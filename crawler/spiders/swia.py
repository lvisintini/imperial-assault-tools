import scrapy
from crawler import items


class ImperialAssaultCrawler(scrapy.Spider):
    name = 'imperial-assault-crawler'
    start_urls = ['http://cards.boardwars.eu/']

    def parse(self, response):
        parser = self.determine_parser(response)
        if parser:
            for item in parser(response):
                yield item
        else:
            next_pages = response.css('.album .albumdesc a::attr(href)')
            next_pages.reverse()
            for next_page in next_pages:
                yield response.follow(next_page, self.parse)

    def get_section(self, response):
        return ''.join(response.css('#gallerytitle h2::text').extract()).strip()

    def get_breadcrumbs(self, response):
        return [bc.strip() for bc in response.css('#gallerytitle h2 > span > a::text').extract()]

    def parse_root(self, response):
        item = items.SourceItem(
            wave=None,
            type='Core Game',
            name='Core Box',
            image=response.css('div.album img ::attr(src)').extract_first().strip(),
        )
        yield item

        next_pages = response.css('.album .albumdesc a::attr(href)')
        next_pages.reverse()
        for next_page in next_pages:
            yield response.follow(next_page, self.parse)

    def parse_extensions(self, response):
        for album in response.css('div.album'):
            yield items.SourceItem(
                type='Expansion',
                wave=None,
                name=album.css('a ::text').extract_first().strip(),
                image=album.css('img ::attr(src)').extract_first().strip(),
            )

            yield response.follow(album.css('a::attr(href)').extract_first(), self.parse)
    '''
    def parse_box(self, response):
        section = self.get_section(response)

        item = items.SourceItem(
            wave=None,
            type='Core Game' if section == 'Core Box' else 'Expansion',
            name=section,
            #image=response.css('div.album img ::attr(src)').extract_first().strip(),
        )
        yield item

        for item in self.parse_source_contents(response):
            yield item

        for next_page in response.css('.album a::attr(href)'):
            yield response.follow(next_page, self.parse)
    '''
    def parse_packs(self, response):
        section = self.get_section(response)
        breadcrumbs = self.get_breadcrumbs(response)

        s_type = 'Ally Pack'
        if 'Agenda Deck' in [album.css('a ::text').extract_first() for album in response.css('div.album')]:
            s_type = 'Villain Pack'

        yield items.SourceItem(
            type=s_type,
            wave=int(breadcrumbs[-1].replace('Wave ', '')),
            name=section,
            image=response.css('div.image img ::attr(src)').extract_first().strip(),
        )

        for item in self.parse_source_contents(response):
            yield item

        for next_page in response.css('.album .albumdesc a::attr(href)'):
            yield response.follow(next_page, self.parse)

    def parse_source_contents(self, response):
        for album in response.css('div.album'):
            yield items.CardBackItem(
                deck=album.css('a ::text').extract_first().strip(),
                variant=None,
                image=album.css('img ::attr(src)').extract_first().strip(),
            )
            yield response.follow(album.css('a::attr(href)').extract_first(), self.parse)

    def parse_skirmish_map(self, response):
        for image in response.css('div.image'):
            yield items.SkirmishMapItem(
                name=image.css('a ::attr(title)').extract_first().strip(),
                image=image.css('img ::attr(src)').extract_first().strip()

            )
            for next_page in response.css('.pagelist .next a::attr(href)'):
                yield response.follow(next_page, self.parse)

    def parse_agenda(self, response):
        for image in response.css('div.image'):
            yield items.AgendaCardItem(
                name=image.css('img ::attr(alt)').extract_first().strip(),
                agenda=self.get_section(response),
                image=image.css('img ::attr(src)').extract_first(),
            )

    def follow_waves(self, response):
        for next_page in response.css('.album .albumdesc  a::attr(href)').extract():
            yield response.follow(next_page, self.parse, priority=int(next_page.split('-')[-1]))

    def determine_parser(self, response):
        section = self.get_section(response)
        breadcrumbs = self.get_breadcrumbs(response)
        if not breadcrumbs:
            return self.parse_root
        elif section in 'Expansion Boxes':
            return self.parse_extensions
        elif section in 'Core Box':
            return self.parse_source_contents
        elif breadcrumbs[-1] in 'Expansion Boxes':
            return self.parse_source_contents
        elif section == 'Villain and Ally Packs':
            return self.follow_waves
        elif breadcrumbs[-1].startswith('Wave '):
            return self.parse_packs
        elif section == 'Skirmish Maps':
            return self.parse_skirmish_map
        elif section == 'Core Box' or breadcrumbs[-1].startswith('Expansion Boxes'):
            return self.parse_source_contents

        elif breadcrumbs[-1].startswith('Agenda') or \
                (section.startswith('Agenda') and 'Villain and Ally Packs' in breadcrumbs):
            return self.parse_agenda
