"""
Bulk-upload product images from a directory.

Usage:
  python manage.py bulk_upload_images /path/to/images/  [--dry-run]

Matching logic:
  1. Strips file extension, replaces _ and - with spaces
  2. Case-insensitive match against Product.name
  3. Also tries prefix match (e.g. "Kuih Kapit" matches "Kuih Kapit Berinti Coklat")
     when no exact match exists

Reports matched, ambiguous, and unmatched files.
"""
import os
import re
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand

from customers.models import Product

VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}


def filename_to_candidate(filepath: Path) -> str:
    """Normalise a filename into a search candidate."""
    stem = filepath.stem
    # Replace underscores and hyphens with spaces
    stem = stem.replace('_', ' ').replace('-', ' ')
    # Collapse multiple spaces
    stem = re.sub(r'\s+', ' ', stem).strip()
    return stem


def find_product(candidate: str, products):
    """Return (product, match_type) or (None, None)."""
    candidate_lower = candidate.lower()

    # 1. Exact match (case-insensitive)
    for p in products:
        if p.name.lower() == candidate_lower:
            return p, 'exact'

    # 2. Prefix / contains match — only if unambiguous
    matches = [p for p in products if p.name.lower().startswith(candidate_lower)]
    if len(matches) == 1:
        return matches[0], 'prefix'

    matches = [p for p in products if candidate_lower in p.name.lower()]
    if len(matches) == 1:
        return matches[0], 'contains'

    return None, None


class Command(BaseCommand):
    help = 'Bulk-upload product images from a directory, matching by filename.'

    def add_arguments(self, parser):
        parser.add_argument('directory', type=str, help='Path to directory containing images')
        parser.add_argument('--dry-run', action='store_true', default=True,
                            help='Show what would be done without saving (default: True)')

    def handle(self, *args, **options):
        directory = Path(options['directory'])
        dry_run = options['dry_run']

        if not directory.is_dir():
            self.stderr.write(self.style.ERROR(f'Directory not found: {directory}'))
            return

        products = list(Product.objects.all())

        image_files = [
            f for f in sorted(directory.iterdir())
            if f.is_file() and f.suffix.lower() in VALID_EXTENSIONS
        ]

        if not image_files:
            self.stderr.write(self.style.WARNING(f'No image files found in {directory}'))
            return

        self.stdout.write(f'Found {len(image_files)} image(s) in {directory}')
        self.stdout.write(f'Products in DB: {len(products)}')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be saved'))
        self.stdout.write('-' * 70)

        matched = 0
        unmatched = []
        ambiguous = []
        skipped = []

        for img_path in image_files:
            candidate = filename_to_candidate(img_path)
            product, match_type = find_product(candidate, products)

            if product:
                if product.image and not dry_run:
                    # Already has an image — skip unless forced
                    self.stdout.write(
                        f'  SKIP  {img_path.name:50s} → {product.name} '
                        f'(already has: {product.image})'
                    )
                    skipped.append((img_path, product))
                    continue

                if not dry_run:
                    with open(img_path, 'rb') as f:
                        product.image.save(img_path.name, File(f), save=True)
                matched += 1
                self.stdout.write(
                    f'  {"[DRY] " if dry_run else "OK    "}'
                    f'{img_path.name:50s} → {product.name}  ({match_type})'
                )
            else:
                # Check if it matches multiple
                candidate_lower = candidate.lower()
                multi = [p for p in products if candidate_lower in p.name.lower()]
                if len(multi) > 1:
                    ambiguous.append((img_path, multi))
                    self.stdout.write(
                        f'  AMBIG {img_path.name:50s} matches: '
                        f'{", ".join(p.name for p in multi[:5])}'
                    )
                else:
                    unmatched.append(img_path)
                    self.stdout.write(
                        f'  NO-MATCH {img_path.name:50s} candidate: "{candidate}"'
                    )

        # Summary
        self.stdout.write('-' * 70)
        self.stdout.write(f'Matched: {matched}  |  Unmatched: {len(unmatched)}  |  '
                          f'Ambiguous: {len(ambiguous)}  |  Skipped: {len(skipped)}')

        if unmatched:
            self.stdout.write('\nUnmatched files (no product found):')
            for f in unmatched:
                self.stdout.write(f'  • {f.name}  → candidate: "{filename_to_candidate(f)}"')

        if ambiguous:
            self.stdout.write('\nAmbiguous files (matched multiple products):')
            for f, prods in ambiguous:
                self.stdout.write(f'  • {f.name}')
                for p in prods:
                    self.stdout.write(f'      — {p.name}')

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS('\nDry run complete. Run with --dry-run false to apply changes.')
            )
