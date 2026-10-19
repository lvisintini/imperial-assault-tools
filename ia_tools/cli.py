"""Fill gaps in imperial-assault-data from cards.boardwars.eu.

  ia audit               crawl the whole gallery and report images the dataset may be missing
  ia scrape <album url>  download one album (a product, or the skirmish maps) into staging/<product>/
  ia enter               open the data-entry app in the browser
  ia import <product>    write a product's entries into the data repo (--check to only validate)
  ia reprocess <product> re-make an imported product's images with the current pipeline (--check to only list them)
"""
import argparse
import json
import sys

from ia_tools import settings


def cmd_audit(args):
    from ia_tools import audit, boardwars
    from ia_tools.dataset import Dataset

    out_dir = settings.STAGING / 'audit'
    if args.rescore:
        report = audit.rescore(Dataset(), out_dir)
    else:
        report = audit.run(boardwars.Client(), Dataset(), out_dir, start_url=args.url)
    print(f"Done: {report['counts']}. Report: {settings.STAGING / 'audit' / 'report.md'}")


def cmd_scrape(args):
    from ia_tools import boardwars, scrape
    from ia_tools.dataset import Dataset

    staging, manifest = scrape.run(boardwars.Client(), Dataset(), args.url, product=args.product)
    print(f"Staged {len(manifest['items'])} images for {manifest['product']} in {staging.dir}")


def cmd_enter(args):
    from ia_tools.enter import server

    server.serve(args.port, open_browser=not args.no_browser)


def cmd_import(args):
    from ia_tools import importer
    from ia_tools.dataset import Dataset
    from ia_tools.staging import Staging

    staging, dataset = Staging(args.product), Dataset()
    if not staging.manifest_path.exists():
        sys.exit(f'Nothing staged for {args.product!r} in {settings.STAGING}')
    try:
        plan = importer.plan(staging, dataset)
    except importer.ImportProblems as problems:
        print(f'{len(problems.problems)} problems:', *problems.problems, sep='\n  ')
        sys.exit(1)
    print(json.dumps(importer.summary(plan), indent=2))
    if args.check:
        return
    log = importer.apply(plan, staging, dataset)
    print(f'Imported into {dataset.root}. Log: {staging.dir / "import-log.json"}')
    if log['upscaled']:
        print('Upscaled (original smaller than the target size):', ', '.join(log['upscaled']))


def cmd_reprocess(args):
    from ia_tools import reprocess
    from ia_tools.dataset import Dataset
    from ia_tools.staging import Staging

    staging, dataset = Staging(args.product), Dataset()
    try:
        todo, log = reprocess.plan(staging, dataset)
    except reprocess.ReprocessProblems as problems:
        print(f'{len(problems.problems)} problems:', *problems.problems, sep='\n  ')
        sys.exit(1)
    cost = f', {2 * len(todo)} TinyPNG compressions' if settings.TINIFY_KEY else ''
    print(f'{len(todo)} images to re-make in {dataset.root} (large and small{cost})')
    if args.check:
        return
    alignments = reprocess.apply(todo, log, staging, dataset, progress=lambda job: print(' ', job[4]))
    unaligned = [key for key, alignment in alignments.items() if alignment is None]
    print(f'Done. Log: {staging.dir / "import-log.json"}')
    if unaligned:
        print('Left unaligned (no template matched well enough; check by eye):', ', '.join(unaligned))


def main(argv=None):
    parser = argparse.ArgumentParser(prog='ia', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)

    audit = commands.add_parser('audit', help='crawl boardwars and report images the dataset may be missing')
    audit.add_argument('url', nargs='?', default='https://cards.boardwars.eu/', help='album to start from')
    audit.add_argument('--rescore', action='store_true',
                       help='rebuild the report from the last run without crawling (after changing hash lists or rules)')
    audit.set_defaults(func=cmd_audit)

    scrape = commands.add_parser('scrape', help='download one album into staging')
    scrape.add_argument('url', help='album URL, e.g. https://cards.boardwars.eu/Expansion-Boxes/Tyrants-of-Lothal/')
    scrape.add_argument('--product', help="product name, when the album doesn't tell (e.g. skirmish maps)")
    scrape.set_defaults(func=cmd_scrape)

    enter = commands.add_parser('enter', help='open the data-entry app')
    enter.add_argument('--port', type=int, default=settings.PORT)
    enter.add_argument('--no-browser', action='store_true', help="don't open a browser")
    enter.set_defaults(func=cmd_enter)

    import_ = commands.add_parser('import', help="write a product's entries into the data repo")
    import_.add_argument('product', help='staging folder name, e.g. tyrants-of-lothal')
    import_.add_argument('--check', action='store_true', help='only validate and show what would change')
    import_.set_defaults(func=cmd_import)

    reprocess = commands.add_parser('reprocess', help="re-make an imported product's images with the current pipeline")
    reprocess.add_argument('product', help='staging folder name, e.g. tyrants-of-lothal')
    reprocess.add_argument('--check', action='store_true', help='only list the images and what it would cost')
    reprocess.set_defaults(func=cmd_reprocess)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    sys.exit(main())
