#!/usr/bin/env python3
"""
CLI tool to normalize OCR-generated text by fixing Latin-Cyrillic character confusion.
"""

import click
import sys
from pathlib import Path
import pymorphy3
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from ingestion.text_normalizer import normalize_cyrillic_latin_mix


# Default list of documents affected by OCR Latin-Cyrillic confusion
DEFAULT_AFFECTED_IDS = [239, 248, 250, 256, 263, 409, 412, 413, 416, 417, 419, 483]


def get_db_session():
    """Create database session from environment or default."""
    # Use SQLite for local development
    db_path = Path(__file__).parent.parent / 'data' / 'teplodar.db'
    engine = create_engine(f'sqlite:///{db_path}')
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal(), engine


def show_diff_sample(original: str, normalized: str, max_chars: int = 200) -> str:
    """Show a sample of changes between original and normalized text."""
    if original == normalized:
        return "No changes"

    # Find first difference
    diff_start = 0
    for i, (o, n) in enumerate(zip(original, normalized)):
        if o != n:
            diff_start = max(0, i - 20)  # Show some context before
            break

    # Extract sample around the difference
    sample_end = min(len(original), diff_start + max_chars)
    orig_sample = original[diff_start:sample_end]
    norm_sample = normalized[diff_start:min(len(normalized), diff_start + max_chars)]

    return f"BEFORE: ...{orig_sample}...\nAFTER:  ...{norm_sample}..."


@click.command()
@click.option('--ids', default=None, help='Comma-separated document IDs to process')
@click.option('--all', is_flag=True, help='Process all documents with OCR text')
@click.option('--dry-run', is_flag=True, help='Show changes without updating database')
def main(ids, all, dry_run):
    """Normalize OCR text by fixing Latin-Cyrillic character confusion."""

    if ids and all:
        click.echo("Error: Cannot specify both --ids and --all", err=True)
        sys.exit(1)

    # Determine which documents to process
    if all:
        target_ids = None  # Process all with char_count > 0
    elif ids:
        try:
            target_ids = [int(x.strip()) for x in ids.split(',')]
        except ValueError:
            click.echo("Error: Invalid ID format. Use comma-separated integers.", err=True)
            sys.exit(1)
    else:
        target_ids = DEFAULT_AFFECTED_IDS

    click.echo("Initializing pymorphy3 analyzer...")
    morph = pymorphy3.MorphAnalyzer()

    click.echo("Connecting to database...")
    session, engine = get_db_session()

    try:
        # Build query
        if target_ids:
            id_list = ','.join(str(id_val) for id_val in target_ids)
            query = f"""
                SELECT id, title, full_text, char_count
                FROM documents
                WHERE id IN ({id_list}) AND full_text IS NOT NULL AND char_count > 0
                ORDER BY id
            """
            result = session.execute(text(query))
        else:
            query = """
                SELECT id, title, full_text, char_count
                FROM documents
                WHERE full_text IS NOT NULL AND char_count > 0
                ORDER BY id
            """
            result = session.execute(text(query))

        documents = result.fetchall()

        if not documents:
            click.echo("No documents found matching criteria.")
            return

        click.echo(f"Found {len(documents)} documents to process.")
        if dry_run:
            click.echo("DRY RUN MODE - no changes will be saved")

        total_docs_changed = 0
        total_replacements = 0

        # Process each document
        for doc in documents:
            doc_id, title, full_text, char_count = doc

            # Normalize the text
            normalized_text, replacements = normalize_cyrillic_latin_mix(full_text, morph)

            if replacements > 0:
                total_docs_changed += 1
                total_replacements += replacements

                click.echo(f"\n--- Document {doc_id}: {title[:50]}{'...' if len(title) > 50 else ''} ---")
                click.echo(f"Replacements: {replacements}")
                click.echo(f"Length: {len(full_text)} → {len(normalized_text)} chars")

                # Show sample of changes
                diff_sample = show_diff_sample(full_text, normalized_text)
                click.echo(f"Sample changes:\n{diff_sample}")

                # Update database if not dry run
                if not dry_run:
                    new_char_count = len(normalized_text)
                    update_query = text("""
                        UPDATE documents
                        SET full_text = :text, char_count = :count
                        WHERE id = :doc_id
                    """)
                    session.execute(update_query, {
                        'text': normalized_text,
                        'count': new_char_count,
                        'doc_id': doc_id
                    })

            else:
                click.echo(f"Document {doc_id}: No changes needed")

        # Commit changes
        if not dry_run and total_replacements > 0:
            session.commit()
            click.echo(f"\n✅ Updated {total_docs_changed} documents in database.")
        elif dry_run and total_replacements > 0:
            click.echo(f"\n📋 DRY RUN: Would update {total_docs_changed} documents.")

        click.echo(f"\nSummary:")
        click.echo(f"- Documents processed: {len(documents)}")
        click.echo(f"- Documents with changes: {total_docs_changed}")
        click.echo(f"- Total character replacements: {total_replacements}")

    except Exception as e:
        session.rollback()
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        session.close()


if __name__ == '__main__':
    main()