import scrapy


class ImperialAssaultCrawler(scrapy.Spider):
    name = 'imperial-assault-crawler'
    start_urls = ['http://cards.boardwars.eu/']

    def parse(self, response):
        [album.css('img ::attr(src)').extract_first() for album in response.css('div.album')]
        [album.css('a ::text').extract_first() for album in response.css('div.album')]
        [album.css('small ::text').extract_first() for album in response.css('div.album')]
        [image.css('img ::attr(src)').extract_first() for image in response.css('div.image')]
        section = ''.join(response.css('#gallerytitle h2::text').extract()).strip()
        bread_crumbs = [bc.strip() for bc in response.css('#gallerytitle h2 > span > a::text').extract()]
        for next_page in response.css('div.album > a'):
            yield response.follow(next_page, self.parse)
        for next_page in response.css('.pagelist .next a'):
            yield response.follow(next_page, self.parse)

    def determine_parser(self, section, breadcrumbs):
        if section == 'Boardwars.eu Imperial Assault Image DB' and not breadcrumbs:
            return self.parse_root
        elif section in 'Expansion Boxes' or breadcrumbs[-1].startswith('Wave '):
            return self.parse_sources
        elif section == 'Core Box' or breadcrumbs[-2].startswith('Wave ') or breadcrumbs[-2] == 'Expansion Boxes':
            return self.parse_source_contents

        elif breadcrumbs[-1] == 'Agenda decks':
            return self.parse_images
        elif section == 'Agenda decks':
            return self.parse_agenda_decks

