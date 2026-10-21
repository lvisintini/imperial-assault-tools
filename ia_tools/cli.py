"""Fill gaps in imperial-assault-data from cards.boardwars.eu.

  ia audit               crawl the whole gallery and report images the dataset may be missing
  ia scrape <album url>  download albums (a product, or the skirmish maps) into staging/<product>/
  ia scrape --gaps       download every image the last audit found unseen into staging/gaps/
  ia propose <type> <id> field=value...   propose a change to an existing record, decided in ia enter
  ia enter               open the data-entry app in the browser
  ia import <product>    write a product's entries into the data repo (--check to only validate)
  ia wiki                cache every product's components and copies from the Imperial Assault wiki in staging/wiki/
                         (--missions: each campaign mission's hero and rewards; --skirmish: skirmish mission cards)
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

    if args.gaps == bool(args.url):
        sys.exit('Pass album URLs or --gaps')
    if args.gaps:
        report = json.loads((settings.STAGING / 'audit' / 'report.json').read_text(encoding='utf-8'))
        staging, manifest = scrape.gaps(boardwars.Client(), Dataset(), report, folder=args.folder or 'gaps')
    else:
        staging, manifest = scrape.run(boardwars.Client(), Dataset(), args.url, product=args.product,
                                       folder=args.folder)
    print(f"Staged {len(manifest['items'])} images for {manifest['product'] or 'several products'} in {staging.dir}")


def cmd_propose(args):
    from ia_tools import edits
    from ia_tools.dataset import Dataset

    changes = {}
    for change in args.changes:
        field, sep, value = change.partition('=')
        if not sep:
            sys.exit(f'Expected field=value, got {change!r}')
        try:
            changes[field] = json.loads(value)  # numbers, null, true, lists
        except json.JSONDecodeError:
            changes[field] = value  # plain text
    dataset = Dataset()
    try:
        record_id = dataset.parse_id(args.content_type, args.id)
        key = edits.propose(dataset, args.folder, args.content_type, record_id, changes, note=args.note)
    except ValueError as error:
        sys.exit(str(error))
    print(f'Proposed {key} in {settings.STAGING / args.folder}; decide it in ia enter')


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


def cmd_wiki(args):
    from ia_tools import boardwars, wiki
    from ia_tools.dataset import Dataset

    if args.skirmish:
        from ia_tools import wiki_skirmish
        cache = wiki_skirmish.run(boardwars.Client(check_robots=False), Dataset(), refresh=args.refresh)
        print(f"{len(cache['missions'])} skirmish missions: {settings.STAGING / 'wiki' / 'skirmish.json'}")
        for mission in cache['missions']:
            for problem in mission['problems']:
                print(f"  {mission['name']}: {problem}")
        return
    if args.missions:
        from ia_tools import wiki_missions
        cache = wiki_missions.run(boardwars.Client(check_robots=False), Dataset(), refresh=args.refresh)
        missions = cache['missions'].values()
        print(f"{len(cache['missions'])} missions, {sum(len(m['rewards']) for m in missions)} reward rows: "
              f"{settings.STAGING / 'wiki' / 'missions.json'}")
        for mission in missions:
            for problem in mission['problems']:
                print(f"  {mission['content_type']} {mission['name']}: {problem}")
        return
    if args.propose:
        try:
            keys = wiki.propose_sources(Dataset(), args.propose)
        except ValueError as error:  # several products on one source, or a dataset without the fields
            sys.exit(str(error))
        print(f'Proposed {len(keys)} source edits from the wiki cache in {settings.STAGING / args.propose}; '
              'decide them in ia enter')
        return
    cache = wiki.run(boardwars.Client(check_robots=False), Dataset(), refresh=args.refresh)
    unmatched = [p['label'] for p in cache['products'] if p['source_id'] is None]
    print(f"{len(cache['products'])} products, {sum(len(p['components']) for p in cache['products'])} components: "
          f"{settings.STAGING / 'wiki' / 'products.json'}")
    print('Not in the dataset\'s sources:', ', '.join(unmatched) or 'none')


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

    scrape = commands.add_parser('scrape', help='download albums into staging')
    scrape.add_argument('url', nargs='*',
                        help='album URL, e.g. https://cards.boardwars.eu/Expansion-Boxes/Tyrants-of-Lothal/')
    scrape.add_argument('--product', help="product name, when the album doesn't tell (e.g. skirmish maps)")
    scrape.add_argument('--folder', help="staging folder name (default: the product's slug); a new one stages more "
                                         'of an already imported product without replacing its staging')
    scrape.add_argument('--gaps', action='store_true',
                        help="instead of albums, every image the last audit found unseen; each names its own product")
    scrape.set_defaults(func=cmd_scrape)

    propose = commands.add_parser('propose', help='propose a change to an existing record, decided in ia enter')
    propose.add_argument('content_type', help='e.g. sources')
    propose.add_argument('id', help='the record id (a number in 1.x data, a UUID from 2.0.0)')
    propose.add_argument('changes', nargs='+', metavar='field=value', help='e.g. name=IG-88 (JSON values: wave=2)')
    propose.add_argument('--folder', default='edits', help='staging folder (default: edits)')
    propose.add_argument('--note', help='why, shown in ia enter')
    propose.set_defaults(func=cmd_propose)

    enter = commands.add_parser('enter', help='open the data-entry app')
    enter.add_argument('--port', type=int, default=settings.PORT)
    enter.add_argument('--no-browser', action='store_true', help="don't open a browser")
    enter.set_defaults(func=cmd_enter)

    import_ = commands.add_parser('import', help="write a product's entries into the data repo")
    import_.add_argument('product', help='staging folder name, e.g. tyrants-of-lothal')
    import_.add_argument('--check', action='store_true', help='only validate and show what would change')
    import_.set_defaults(func=cmd_import)

    wiki_ = commands.add_parser('wiki', help="cache every product's components and copies from the wiki")
    wiki_.add_argument('--refresh', action='store_true', help='fetch the pages again instead of reusing the cache')
    wiki_.add_argument('--propose', nargs='?', const='wiki-sources', metavar='FOLDER',
                       help="instead, stage edits to every source's code, dates, wave and type from the cache, "
                            'decided in ia enter (default folder: wiki-sources)')
    wiki_.add_argument('--missions', action='store_true',
                       help="cache each campaign mission's hero and rewards (staging/wiki/missions.json) instead")
    wiki_.add_argument('--skirmish', action='store_true',
                       help='cache every skirmish mission card, its map and format, and its image '
                            '(staging/wiki/skirmish.json) instead')
    wiki_.set_defaults(func=cmd_wiki)

    reprocess = commands.add_parser('reprocess', help="re-make an imported product's images with the current pipeline")
    reprocess.add_argument('product', help='staging folder name, e.g. tyrants-of-lothal')
    reprocess.add_argument('--check', action='store_true', help='only list the images and what it would cost')
    reprocess.set_defaults(func=cmd_reprocess)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    sys.exit(main())
