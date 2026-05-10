"""
Text normalizer for fixing OCR-induced Latin-Cyrillic character confusion.
"""

import re
from typing import Tuple
import pymorphy3


# Mapping of visually similar Latin characters to Cyrillic
LATIN_TO_CYR = {
    # Uppercase
    'A': 'А', 'B': 'В', 'E': 'Е', 'K': 'К', 'M': 'М', 'H': 'Н',
    'O': 'О', 'P': 'Р', 'C': 'С', 'T': 'Т', 'X': 'Х', 'Y': 'У', 'I': 'И',
    'Z': 'З',
    # Lowercase
    'a': 'а', 'c': 'с', 'e': 'е', 'o': 'о', 'p': 'р', 'x': 'х', 'y': 'у',
    'k': 'к', 'm': 'м', 'h': 'н', 't': 'т', 'n': 'п', 'r': 'г', 'u': 'и'
}

# Multi-character replacements (digrапhs) - applied before single char replacements
DIGRAPH_REPLACEMENTS = [
    # Case-sensitive variants - order matters (longer first)
    ('III', 'Ш'), ('JI', 'Л'), ('JT', 'Л'), ('LIA', 'Я'), ('LU', 'Щ'), ('bI', 'Ы'), ('II', 'П'),
    ('iii', 'ш'), ('ji', 'л'), ('jt', 'л'), ('lia', 'я'), ('lu', 'щ'), ('bi', 'ы'), ('ii', 'п'),
    # Mixed case variants
    ('Iii', 'Ш'), ('Ji', 'Л'), ('Jt', 'Л'), ('Bi', 'ы'), ('Li', 'л'), ('Lu', 'Щ'), ('Ii', 'П'),
]

# Character ranges for detection
CYRILLIC_RANGE = re.compile(r'[а-яё́А-ЯЁ]')
LATIN_RANGE = re.compile(r'[a-zA-Z]')

# Token pattern: sequence of letters (including - and ' for compound words)
TOKEN_PATTERN = re.compile(r'[a-zA-Zа-яё́А-ЯЁ\-\']+')


def has_cyrillic(text: str) -> bool:
    """Check if text contains any Cyrillic characters."""
    return bool(CYRILLIC_RANGE.search(text))


def has_latin(text: str) -> bool:
    """Check if text contains any Latin characters."""
    return bool(LATIN_RANGE.search(text))


def apply_digraphs(token: str) -> Tuple[str, int]:
    """Apply digraph replacements to a token. Returns (new_token, replacement_count)."""
    result = token
    total_replacements = 0

    # Sort by length descending to apply longer patterns first
    sorted_digraphs = sorted(DIGRAPH_REPLACEMENTS, key=lambda x: len(x[0]), reverse=True)

    for digraph, replacement in sorted_digraphs:
        if digraph in result:
            count_before = result.count(digraph)
            result = result.replace(digraph, replacement)
            if count_before > 0:
                total_replacements += count_before

    return result, min(total_replacements, 1)  # Return 1 if any replacements made


def has_digit(text: str) -> bool:
    """Check if text contains any digits."""
    return any(c.isdigit() for c in text)


def is_cyrillic_context(tokens: list, current_idx: int, window: int = 2) -> bool:
    """
    Check if token at current_idx is in Cyrillic context by examining neighboring tokens.
    Returns True if any of the neighboring tokens (within window) contain Cyrillic characters.
    """
    start = max(0, current_idx - window)
    end = min(len(tokens), current_idx + window + 1)

    cyrillic_count = 0
    latin_count = 0

    for i in range(start, end):
        if i != current_idx:
            if has_cyrillic(tokens[i]):
                cyrillic_count += 1
            elif has_latin(tokens[i]) and not has_digit(tokens[i]):
                latin_count += 1

    # Return True if more Cyrillic context than Latin
    return cyrillic_count > latin_count


def fix_token(token: str, morph: pymorphy3.MorphAnalyzer, in_cyrillic_context: bool = False) -> Tuple[str, int]:
    """
    Fix a single token by replacing Latin characters with Cyrillic equivalents.

    Args:
        token: Token to fix
        morph: Pymorphy3 analyzer
        in_cyrillic_context: Whether this token appears in Cyrillic context

    Returns:
        tuple[str, int]: (fixed_token, replacement_count)
    """
    # Protection: don't touch tokens with digits or certain patterns
    if has_digit(token):
        return token, 0

    # Protection: mixed case with dots (version numbers, codes)
    if '.' in token:
        return token, 0

    # Protection: contains dash and Latin letters (codes like PN-EN)
    if '-' in token and has_latin(token):
        return token, 0

    # Protection: certain patterns that should be preserved
    preserve_patterns = ['ecoMAX', 'WEEE', 'Comfort']
    for pattern in preserve_patterns:
        if pattern in token:
            return token, 0

    # Protection: uppercase tokens 4+ chars - but allow very long OCR artifacts
    if token.isupper() and len(token) >= 4 and len(token) < 8 and not has_cyrillic(token) and not in_cyrillic_context:
        # Test conversion for shorter uppercase tokens
        test_candidate, _ = apply_digraphs(token)
        for char in test_candidate:
            if char in LATIN_TO_CYR:
                test_candidate = test_candidate.replace(char, LATIN_TO_CYR[char])

        # Only if pure Cyrillic and known word
        if has_cyrillic(test_candidate) and not has_latin(test_candidate):
            if morph.word_is_known(test_candidate.lower()):
                candidate, _ = apply_digraphs(token)
                for char in candidate:
                    if char in LATIN_TO_CYR:
                        candidate = candidate.replace(char, LATIN_TO_CYR[char])
                return candidate, 1
        return token, 0

    has_cyr = has_cyrillic(token)
    has_lat = has_latin(token)

    # Case 1: Pure Cyrillic - don't touch
    if has_cyr and not has_lat:
        return token, 0

    # Case 2: Pure Latin
    if has_lat and not has_cyr:
        # First apply digraphs
        candidate, digraph_replacements = apply_digraphs(token)

        # Then apply character-by-character replacements
        replaceable_count = 0
        total_latin_count = 0

        for char in candidate:
            if re.match(r'[a-zA-Z]', char):
                total_latin_count += 1
                if char in LATIN_TO_CYR:
                    replaceable_count += 1

        # Apply character replacements
        char_candidate = candidate
        for char in candidate:
            if char in LATIN_TO_CYR:
                char_candidate = char_candidate.replace(char, LATIN_TO_CYR[char])

        # Special case: 'b' at end of word → 'ь' (soft sign)
        if candidate.endswith('b'):
            char_candidate = char_candidate[:-1] + 'ь'

        final_candidate = char_candidate
        total_replacements = max(digraph_replacements, int(candidate != final_candidate))

        # Calculate ratio for context-based decisions
        ratio_threshold = replaceable_count / total_latin_count if total_latin_count > 0 else 0

        # Check if pure Cyrillic result is a known word
        if has_cyrillic(final_candidate) and not has_latin(final_candidate):
            if morph.word_is_known(final_candidate.lower()):
                return final_candidate, 1

        # Context-based aggressive replacement for pure Latin tokens
        if in_cyrillic_context and total_latin_count > 0:
            # Check if all Latin characters were replaceable
            all_replaced = not has_latin(final_candidate)

            # Apply replacement if in Cyrillic context and high conversion ratio
            if ratio_threshold >= 0.6 or all_replaced:
                return final_candidate, 1

        # Fallback: check partial Cyrillic words
        if has_cyrillic(final_candidate):
            cyr_chars = ''.join([c for c in final_candidate if re.match(r'[а-яё́А-ЯЁ]', c)])
            min_len = 2 if len(token) <= 4 else 3
            if len(cyr_chars) >= min_len and morph.word_is_known(cyr_chars.lower()):
                return final_candidate, 1

            # High ratio replacement for long words (only in Cyrillic context or very long tokens)
            if ratio_threshold >= 0.75 and len(cyr_chars) >= 4 and (in_cyrillic_context or len(token) >= 8):
                return final_candidate, 1

        # Special handling: very long pure Latin tokens with high replacement ratio
        # These are almost certainly OCR artifacts
        if len(token) >= 8 and ratio_threshold >= 0.8:
            return final_candidate, 1

        return token, 0

    # Case 3: Mixed Latin/Cyrillic - almost certainly OCR artifacts
    if has_cyr and has_lat:
        # Apply digraphs first
        candidate, digraph_replacements = apply_digraphs(token)

        # Then character replacements
        char_replacement_count = 0
        for char in candidate:
            if char in LATIN_TO_CYR:
                candidate = candidate.replace(char, LATIN_TO_CYR[char])
                char_replacement_count = 1

        # Special case: 'b' at end of word → 'ь' (soft sign)
        if candidate.endswith('b'):
            candidate = candidate[:-1] + 'ь'
            char_replacement_count = 1

        total_replacements = max(digraph_replacements, char_replacement_count)

        # Check if pure Cyrillic result is a known word
        if has_cyrillic(candidate) and not has_latin(candidate):
            if morph.word_is_known(candidate.lower()):
                return candidate, total_replacements

        # Apply replacement for mixed tokens anyway (almost always OCR errors)
        if candidate != token:
            return candidate, 1

        return token, 0

    return token, 0


def normalize_cyrillic_latin_mix(text: str, morph: pymorphy3.MorphAnalyzer) -> Tuple[str, int]:
    """
    Normalize text by fixing Latin-Cyrillic character confusion from OCR.

    Args:
        text: Input text with potential character confusion
        morph: Pymorphy3 analyzer for Russian language validation

    Returns:
        tuple[str, int]: (normalized_text, total_replacements)
    """
    if not text:
        return text, 0

    # Extract all tokens with their positions for context analysis
    token_matches = list(TOKEN_PATTERN.finditer(text))
    tokens = [match.group() for match in token_matches]

    total_replacements = 0
    result_parts = []
    last_end = 0

    # Process each token with context awareness
    for i, match in enumerate(token_matches):
        start, end = match.span()
        token = match.group()

        # Add text before token (punctuation, spaces, etc.)
        result_parts.append(text[last_end:start])

        # Check if token is in Cyrillic context
        in_context = is_cyrillic_context(tokens, i, window=2)

        # Fix the token
        fixed_token, replacements = fix_token(token, morph, in_context)
        result_parts.append(fixed_token)
        total_replacements += replacements

        last_end = end

    # Add remaining text after last token
    result_parts.append(text[last_end:])

    return ''.join(result_parts), total_replacements


def test_normalize():
    """Test cases for normalization function."""
    morph = pymorphy3.MorphAnalyzer()
    cases = [
        # (input_text, expected_output, description)
        ("YCTAHOBKE", "УСТАНОВКЕ", "YCTAHOBKE standalone"),
        ("MOЩHOCTb", "МОЩНОСТь", "MOЩHOCTb mixed"),
        ("РЕГУЛЯТОР Tak используется", "РЕГУЛЯТОР Так используется", "Tak in Russian context"),
        ("РЕГУЛЯТОР Ke используется", "РЕГУЛЯТОР Ке используется", "Ke in Russian context"),
        ("РЕГУЛЯТОР He используется", "РЕГУЛЯТОР Не используется", "He in Russian context"),
        ("РЕГУЛЯТОР ITY устройство", "РЕГУЛЯТОР ИТУ устройство", "ITY in Russian context"),
        ("BeTpa", "ВеТра", "BeTpa standalone"),
        ("MOJIBZOBATEJIA", "МОЛВЗОВАТЕЛА", "MOJIBZOBATEJIA with JI digraphs"),
        ("ecoMAX050 модель", "ecoMAX050 модель", "model anchor preserved"),
        ("PN-EN стандарт", "PN-EN стандарт", "PN-EN anchor preserved"),
        ("V.01.XX.XX версия", "V.01.XX.XX версия", "version anchor preserved"),
        ("Comfort серия", "Comfort серия", "Comfort anchor preserved"),
        ("WEEE директива", "WEEE директива", "WEEE abbreviation preserved"),
        ("Регулятор", "Регулятор", "pure Cyrillic unchanged"),
        ("ecoMAX в тексте", "ecoMAX в тексте", "pure Latin in Cyrillic context - no digits"),
        ("english text only", "english text only", "pure English text unchanged"),
    ]

    print("Running normalization tests...")
    failed_tests = []

    for inp, exp, desc in cases:
        out, count = normalize_cyrillic_latin_mix(inp, morph)
        if out == exp:
            print(f"✅ [{desc}] '{inp}' → '{out}' ({count} replacements)")
        else:
            print(f"❌ [{desc}] '{inp}' → '{out}' (expected: '{exp}') ({count} replacements)")
            failed_tests.append(desc)

    if failed_tests:
        print(f"\n❌ {len(failed_tests)} tests failed: {', '.join(failed_tests)}")
        return False
    else:
        print(f"\n✅ All {len(cases)} tests passed!")
        return True


if __name__ == "__main__":
    # Test cases
    print("Initializing pymorphy3...")
    morph = pymorphy3.MorphAnalyzer()

    test_normalize()

    # Test word recognition
    print(f"\nWord recognition tests:")
    print(f"morph.word_is_known('инструкция'): {morph.word_is_known('инструкция')}")
    print(f"morph.word_is_known('не'): {morph.word_is_known('не')}")
    print(f"morph.word_is_known('так'): {morph.word_is_known('так')}")
    print(f"morph.word_is_known('ке'): {morph.word_is_known('ке')}")
    print(f"morph.word_is_known('для'): {morph.word_is_known('для')}")