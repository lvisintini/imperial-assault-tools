"""Fill gaps in imperial-assault-data from cards.boardwars.eu.

  ia audit               crawl the whole gallery and report images the dataset may be missing
  ia scrape <album url>  download albums (a product, or the skirmish maps) into staging/<product>/
  ia scrape --gaps       download every image the last audit found unseen into staging/gaps/
  ia stage <slug> --type <type> [files] [--tts save.zip]   stage images that aren't on boardwars
  ia propose <type> <id> field=value...   propose a change to an existing record, decided in ia enter
  ia enter               open the data-entry app in the browser
  ia import <product>    write a product's entries into the data repo (--check to only validate)
  ia wiki                cache every product's components and copies from the Imperial Assault wiki in staging/wiki/
                         (--missions: each campaign mission's hero and rewards; --skirmish: skirmish mission cards)
  ia reprocess <product> re-make an imported product's images with the current pipeline (--check to only list them)
  ia ic2                 cache ImperialCommander2's map tile sizes and campaign mission layouts in staging/ic2/
  ia tiles [module]      stage the Vassal module's map tiles and IC2's campaign layouts in staging/map-tiles/
  ia sheets [dir]        turn the scanned rules sheets (Sheets/<product>/, two pages each) into PDFs in staging/sheets/
  ia maps [--sample ...] draw the campaign maps from IC2's layouts and the Vassal tiles in staging/campaign-maps/
  ia layouts             write the map layouts entered in ia enter (Map layouts) into the data repo (--check to only
                         validate)
  ia card-types --fetch  cache the wiki's text of the reward Feats and Imperial class cards, to propose which are a
                         Group Attachment on ia enter's Card types page
  ia card-types          write the card types confirmed in ia enter into the data repo (--check to only validate)
  ia mats                stage the 13 skirmish map mats as sources (wiki values, images from FFG's archived product
                         pages) in staging/mats/, for the data repo's migration 19
  ia missions            write the skirmish scenarios and story mission rewards entered in ia enter (Missions) into the
                         data repo (--check to only validate)
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


def cmd_stage(args):
    from ia_tools import stage_local
    from ia_tools.dataset import Dataset

    try:
        staging, manifest = stage_local.run(Dataset(), args.slug, args.type, args.files, args.tts, args.product)
    except ValueError as error:
        sys.exit(str(error))
    print(f"Staged {len(manifest['items'])} images in {staging.dir}; name them in ia enter")


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


def cmd_ic2(args):
    import requests

    from ia_tools import ic2

    cache = ic2.run(requests.Session(), log=lambda line: None)
    print(f"{len(cache['tiles'])} tiles, {len(cache['missions'])} missions: {settings.STAGING / 'ic2' / 'ic2.json'}")


def cmd_tiles(args):
    from ia_tools import ic2, tiles
    from ia_tools.dataset import Dataset

    manifest, problems = tiles.run(args.module, ic2.load(), Dataset())
    if problems:
        print(f'{len(problems)} problems:', *problems, sep='\n  ')
        sys.exit(1)
    print(json.dumps(manifest['checks'], indent=2))
    print(f"Staged in {settings.STAGING / 'map-tiles'}; fill in copies.csv")


def cmd_sheets(args):
    from ia_tools import sheets
    from ia_tools.dataset import Dataset

    made, problems = sheets.run(args.dir, Dataset().records('sources'), check=args.check)
    if problems:
        print(f'{len(problems)} problems:', *problems, sep='\n  ')
        sys.exit(1)
    if args.check:
        for sheet in made:
            print(f"  {sheet['folder']} → {sheet['file']}: {' + '.join(sheet['pages'])}")
        return
    print(f"{len(made)} sheets, {sum(s['bytes'] for s in made) / 1e6:.0f} MB: {settings.STAGING / 'sheets'}")


def cmd_maps(args):
    import requests

    from ia_tools import campaign_maps, ic2
    from ia_tools.dataset import Dataset

    textures = ic2.fetch_textures(requests.Session())
    manifest, problems = campaign_maps.run(args.module, ic2.load(), textures, Dataset(), sample=args.sample)
    by = {}
    for turn in manifest['turns'].values():
        by[turn['by']] = by.get(turn['by'], 0) + 1
    print(f"{len(manifest['maps'])} maps; tile sides turned by {by}: {settings.STAGING / 'campaign-maps'}")
    if problems:
        print(f'{len(problems)} problems:', *problems, sep='\n  ')
        sys.exit(1)


def cmd_layouts(args):
    from ia_tools import layouts
    from ia_tools.dataset import Dataset

    summary, problems = layouts.run(Dataset(), check=args.check)
    print(json.dumps(summary, indent=2))
    if problems:
        print(f'{len(problems)} problems:', *problems, sep='\n  ')
        sys.exit(1)
    if not args.check:
        print(f"Wrote {summary['done']} maps' layouts into map-layouts.json")


def cmd_mats(args):
    from ia_tools import boardwars, mats
    from ia_tools.dataset import Dataset

    manifest, problems = mats.run(boardwars.Client(check_robots=False), Dataset())
    if problems:
        print(f'{len(problems)} problems:', *problems, sep='\n  ')
        sys.exit(1)
    for mat in manifest['mats']:
        print(f"{mat['product_code']} {mat['name']}: wave {mat['wave']}, released {mat['release_date']}, map "
              f"{mat['map']}{', upscaled' if mat['upscaled'] else ''}")
    print(f"Staged {len(manifest['mats'])} mats in {mats.out_dir()}")


def cmd_card_types(args):
    from ia_tools import boardwars, card_types
    from ia_tools.dataset import Dataset

    dataset = Dataset()
    if args.fetch:
        pages = card_types.fetch(boardwars.Client(check_robots=False), dataset, refresh=args.refresh)
        found = card_types.proposals(dataset, pages)
        flagged = {card_id: p for card_id, p in found.items() if p['flags']}
        print(f'{len(found)} cards, {len(pages)} with a wiki page, {len(flagged)} flagged for a closer look')
        return
    summary, problems = card_types.run(dataset, check_only=args.check)
    print(json.dumps(summary, indent=2))
    if problems:
        print(f'{len(problems)} problems:', *problems[:20], sep='\n  ')
        sys.exit(1)
    if not args.check:
        print(f"Wrote {summary['done']} cards' type")


def cmd_missions(args):
    from ia_tools import mission_entries
    from ia_tools.dataset import Dataset

    summary, problems = mission_entries.run(Dataset(), check=args.check)
    print(json.dumps(summary, indent=2))
    if problems:
        print(f'{len(problems)} problems:', *problems, sep='\n  ')
        sys.exit(1)
    if not args.check:
        print(f"Wrote {summary['scenarios']} scenarios and {summary['rows']} story mission rewards")


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

    stage = commands.add_parser('stage', help="stage images that aren't on boardwars (files, a TTS save)")
    stage.add_argument('slug', help='staging folder name')
    stage.add_argument('files', nargs='*', help='image files')
    stage.add_argument('--type', required=True, help='the content type the images are (backs: its card backs)')
    stage.add_argument('--tts', metavar='SAVE', help='a Tabletop Simulator saved object (.zip with its images)')
    stage.add_argument('--product', help='the existing product the images belong to, if any')
    stage.set_defaults(func=cmd_stage)

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

    ic2_ = commands.add_parser('ic2', help="cache ImperialCommander2's tile sizes and campaign layouts")
    ic2_.set_defaults(func=cmd_ic2)

    tiles_ = commands.add_parser('tiles', help="stage the Vassal module's map tiles and IC2's campaign layouts")
    tiles_.add_argument('module', nargs='?', default=settings.TOOLS_ROOT / 'vassal',
                        help='the extracted Vassal campaign module (buildFile, images/, Aftermath.vsav)')
    tiles_.set_defaults(func=cmd_tiles)

    sheets = commands.add_parser('sheets', help='turn the scanned rules sheets into PDFs in staging/sheets/')
    sheets.add_argument('dir', nargs='?', default=settings.TOOLS_ROOT / 'Sheets', help='one folder of scans per sheet')
    sheets.add_argument('--check', action='store_true', help='only list each folder, its product and page order')
    sheets.set_defaults(func=cmd_sheets)

    maps = commands.add_parser('maps', help="draw the campaign maps from IC2's layouts and the Vassal tiles")
    maps.add_argument('module', nargs='?', default=settings.TOOLS_ROOT / 'vassal', help='the extracted Vassal module')
    maps.add_argument('--sample', nargs='+', metavar='MISSION', help='only these missions (IC2 names)')
    maps.set_defaults(func=cmd_maps)

    layouts = commands.add_parser('layouts', help='write the map layouts entered in ia enter into the data repo')
    layouts.add_argument('--check', action='store_true', help='only validate the entries')
    layouts.set_defaults(func=cmd_layouts)

    mats_ = commands.add_parser('mats', help="stage the skirmish map mats as sources, with images from FFG's archived "
                                             'product pages')
    mats_.set_defaults(func=cmd_mats)

    card_types_ = commands.add_parser('card-types', help='propose card types from the wiki, and write the '
                                                         'ones confirmed in ia enter into the data repo')
    card_types_.add_argument('--fetch', action='store_true', help="cache the cards' wiki pages")
    card_types_.add_argument('--refresh', action='store_true', help='with --fetch, fetch cached pages again')
    card_types_.add_argument('--check', action='store_true', help='only validate the entries')
    card_types_.set_defaults(func=cmd_card_types)

    missions = commands.add_parser('missions', help='write the scenarios and story rewards entered in ia enter into the '
                                                    'data repo')
    missions.add_argument('--check', action='store_true', help='only validate the entries')
    missions.set_defaults(func=cmd_missions)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    sys.exit(main())
