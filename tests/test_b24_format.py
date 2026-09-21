import pytest

from src.b24.format import html_to_bbcode


@pytest.mark.parametrize("html, expected", [
    ("<b>Русь-12 Л</b> подойдёт", "[b]Русь-12 Л[/b] подойдёт"),
    ("<i>курсив</i> и <code>код</code>", "[i]курсив[/i] и [code]код[/code]"),
    ("<strong>a</strong><em>b</em>", "[b]a[/b][i]b[/i]"),
    ("строка 1<br>строка 2<br/>строка 3", "строка 1\nстрока 2\nстрока 3"),
    ('<a href="https://teplodar.ru/catalog/detail/kaskad_12_t/">Каскад 12 Т</a>',
     "[url=https://teplodar.ru/catalog/detail/kaskad_12_t/]Каскад 12 Т[/url]"),
    ('<a href="https://x.ru/a_b_c/">https://x.ru/a_b_c/</a>', "[url]https://x.ru/a_b_c/[/url]"),
    ("<a href='https://x.ru/?a=1&amp;b=2'>x</a>", "[url=https://x.ru/?a=1&b=2]x[/url]"),
    ('<a href="https://x.ru/"><b>жирная</b> ссылка</a>', "[url=https://x.ru/][b]жирная[/b] ссылка[/url]"),
    ("Цена &lt; 30&nbsp;000 &amp; доставка", "Цена < 30\xa0000 & доставка"),
    ("&lt;b&gt;не тег&lt;/b&gt;", "<b>не тег</b>"),
    ("<ul><li>один</li><li>два</li></ul>", "• один\n• два"),
    ("<p>абзац</p><p>второй</p>", "абзац\n\nвторой"),
    ("<span class=x>чужой</span> тег", "чужой тег"),
    ("a\n\n\n\n\nb", "a\n\nb"),
    ("", ""),
    (None, ""),
])
def test_html_to_bbcode(html, expected):
    assert html_to_bbcode(html) == expected


def test_real_answer_shape():
    html = (
        "Для парной 14 м³ подойдут:<br><br>"
        "1. <b>Русь-12 Л</b> — 8–14 м³, цена <b>28 900 ₽</b>.<br>"
        "Ссылка: https://teplodar.ru/catalog/detail/rus_12_l/<br><br>"
        "2. <b>Сахара-16 ЛК</b> — 8–16 м³.<br>"
        "<a href=\"https://teplodar.ru/catalog/detail/sahara_16_lk/\">Подробнее</a>"
    )
    bb = html_to_bbcode(html)
    assert "[b]Русь-12 Л[/b]" in bb
    assert "https://teplodar.ru/catalog/detail/rus_12_l/" in bb          # bare URL untouched
    assert "[url=https://teplodar.ru/catalog/detail/sahara_16_lk/]Подробнее[/url]" in bb
    assert "<" not in bb and "&" not in bb
