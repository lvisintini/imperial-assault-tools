import scrapy
from crawler import items


class ImperialAssaultCrawler(scrapy.Spider):
    name = 'imperial-assault-crawler'
    start_urls = ['http://cards.boardwars.eu/']

    max_levels = 2

    ids = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def parse(self, response):
        #[album.css('img ::attr(src)').extract_first() for album in response.css('div.album')]
        #[album.css('a ::text').extract_first() for album in response.css('div.album')]
        #[album.css('small ::text').extract_first() for album in response.css('div.album')]
        #[image.css('img ::attr(src)').extract_first() for image in response.css('div.image')]
        #section = ''.join(response.css('#gallerytitle h2::text').extract()).strip()
        #bread_crumbs = [bc.strip() for bc in response.css('#gallerytitle h2 > span > a::text').extract()]

        parser = self.determine_parser(response)
        if parser:
            for item in parser(response):
                yield item

        if response.meta.get('depth', 0) <= self.max_levels:
            next_pages = response.css('.album a')
            next_pages.reverse()
            for next_page in next_pages:
                yield response.follow(
                    next_page,
                    self.parse,
                    meta={'ids': self.ids.copy()}
                )

        for next_page in response.css('.pagelist .next a'):
             yield response.follow(next_page, self.parse)

    def get_section(self, response):
        return ''.join(response.css('#gallerytitle h2::text').extract()).strip()

    def get_breadcrumbs(self, response):
        return [bc.strip() for bc in response.css('#gallerytitle h2 > span > a::text').extract()]

    def get_next_id(self, m):
        inc = self.ids.get(f'{m}_inc_id', -1)
        inc += 1
        self.ids[f'{m}_inc_id'] = inc
        return inc

    def parse_root(self, response):
        yield items.SourceItem(
            id=self.get_next_id('source'),
            name=response.css('div.album a ::text').extract_first().strip(),
            image=response.css('div.album img ::attr(src)').extract_first().strip(),
        )

    def parse_sources(self, response):
        for album in response.css('div.album'):
            name = album.css('a ::text').extract_first().replace('Box', '').strip()
            if name == 'Jabbas-Realm':
                name = "Jabba's Realm"

            yield items.SourceItem(
                id=self.get_next_id('source'),
                type='Expansion',
                wave=None,
                name=name,
                image=album.css('img ::attr(src)').extract_first().strip(),
            )

    def parse_packs(self, response):
        section = self.get_section(response)
        breadcrumbs = self.get_breadcrumbs(response)

        s_type = 'Ally Pack'
        if 'Agenda Deck' in [album.css('a ::text').extract_first() for album in response.css('div.album')]:
            s_type = 'Villain Pack'

        yield items.SourceItem(
            id=self.get_next_id('source'),
            type=s_type,
            wave=int(breadcrumbs[-1].replace('Wave ', '')),
            name=section,
            image=response.css('div.image img ::attr(src)').extract_first().strip(),
        )

        #for item in self.parse_source_contents(response):
        #    yield item

    def parse_source_contents(self, response):
        pass

    def parse_skirmish_map(self, response):
        for image in response.css('div.image'):
            yield items.SkirmishMapItem(
                name=image.css('a ::attr(title)').extract_first().strip(),
                image=image.css('img ::attr(src)').extract_first().strip()

            )

    def determine_parser(self, response):
        section = self.get_section(response)
        breadcrumbs = self.get_breadcrumbs(response)
        if section == 'Boardwars.eu Imperial Assault Image DB' and not breadcrumbs:
            return self.parse_root
        elif section in 'Expansion Boxes':
            return self.parse_sources
        elif breadcrumbs[-1].startswith('Wave '):
            return self.parse_packs
        elif section == 'Skirmish Maps':
            return self.parse_skirmish_map
        '''
        elif section == 'Core Box' or breadcrumbs[-2].startswith('Wave ') or breadcrumbs[-2] == 'Expansion Boxes':
            return self.parse_source_contents
        elif breadcrumbs[-1] == 'Agenda decks':
            return self.parse_images
        elif section == 'Agenda decks':
            return self.parse_agenda_decks
        '''

