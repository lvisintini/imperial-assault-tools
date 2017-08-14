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
            wave=int(breadcrumbs[-1].lower().replace('wave ', '').replace('wave-', '')),
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
        elif breadcrumbs[-1].lower().startswith('wave'):
            return self.parse_packs
        elif section == 'Skirmish Maps':
            return self.parse_skirmish_map
        elif section == 'Core Box' or breadcrumbs[-1].startswith('Expansion Boxes'):
            return self.parse_source_contents

        elif breadcrumbs[-1].startswith('Agenda') or \
                (section.startswith('Agenda') and 'Villain and Ally Packs' in breadcrumbs):
            return self.parse_agenda

'''

 'source': 4}
DEBUG:scrapy.core.scraper:Scraped from <200 http://cards.boardwars.eu/index.php?album=Core-Box/Agenda%20Decks/Agents%20of%20the%20Empire>
{'agenda': 'Agents of the Empire',
 'image': '/cache/Core-Box/Agenda%20Decks/Agents%20of%20the%20Empire/Tracking%20Beacon_275_thumb_ffflogog_whatermark_cc.jpg',
 'name': 'Tracking Beacon',
 'source': 4}
DEBUG:scrapy.core.engine:Crawled (200) <GET http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-9> (referer: http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs)
DEBUG:scrapy.core.engine:Crawled (200) <GET http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-8> (referer: http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs)
DEBUG:scrapy.core.engine:Crawled (200) <GET http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-7> (referer: http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs)
DEBUG:scrapy.core.engine:Crawled (200) <GET http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-6> (referer: http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs)
DEBUG:scrapy.core.engine:Crawled (200) <GET http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-5> (referer: http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs)
DEBUG:scrapy.core.engine:Crawled (200) <GET http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-4> (referer: http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs)
DEBUG:scrapy.core.engine:Crawled (200) <GET http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-3> (referer: http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs)
DEBUG:scrapy.core.engine:Crawled (200) <GET http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-2> (referer: http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs)
DEBUG:scrapy.core.engine:Crawled (200) <GET http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-1> (referer: http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs)
DEBUG:scrapy.core.engine:Crawled (200) <GET http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-2/Boba%20Fett> (referer: http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-2)
DEBUG:scrapy.core.scraper:Scraped from <200 http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-2/Boba%20Fett>
{'id': 5,
 'image': '/cache/Ally-and-Villain-Packs/Wave-2/Boba%20Fett/Boba%20Fett%20Pack_275_thumb_ffflogog_whatermark_cc.png',
 'name': 'Boba Fett',
 'type': 'Villain Pack',
 'wave': 2}
WARNING:scrapy.core.scraper:Dropped: 
{'deck': 'Agenda',
 'image': '/cache/Ally-and-Villain-Packs/Wave-2/Boba%20Fett/Agenda%20Deck/back_275_thumb_ffflogog_whatermark_cc.jpg',
 'variant': None}
WARNING:scrapy.core.scraper:Dropped: 
{'deck': 'Command',
 'image': '/cache/Ally-and-Villain-Packs/Wave-2/Boba%20Fett/Command%20Cards/back_275_thumb_ffflogog_whatermark_cc.jpg',
 'variant': None}
WARNING:scrapy.core.scraper:Dropped: 
{'deck': 'Deployment',
 'image': '/cache/Ally-and-Villain-Packs/Wave-2/Boba%20Fett/Deployment%20Cards/Back_275_thumb_ffflogog_whatermark_cc.jpg',
 'variant': None}
DEBUG:scrapy.dupefilters:Filtered duplicate request: <GET http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-2/Boba%20Fett/Agenda%20Deck> - no more duplicates will be shown (see DUPEFILTER_DEBUG to show all duplicates)
DEBUG:scrapy.core.engine:Crawled (200) <GET http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-1/Chewbacca> (referer: http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-1)
DEBUG:scrapy.core.scraper:Scraped from <200 http://cards.boardwars.eu/index.php?album=Ally-and-Villain-Packs/Wave-1/Chewbacca>
{'id': 6,
 'image': '/cache/Ally-and-Villain-Packs/Wave-1/Chewbacca/Chewbacca%20Pack_275_thumb_ffflogog_whatermark_cc.png',
 'name': 'Chewbacca',
 'type': 'Ally Pack',
 'wave': 1}
WARNING:scrapy.core.scraper:Dropped: 
{'deck': 'Command',
 'image': '/cache/Ally-and-Villain-Packs/Wave-1/Chewbacca/Command%20Cards/back_275_thumb_ffflogog_whatermark_cc.jpg',
 'variant': None}
WARNING:scrapy.core.scraper:Dropped: 
{'deck': 'Deployment',
 'image': '/cache/Ally-and-Villain-Packs/Wave-1/Chewbacca/Deployment%20Cards/Back_275_thumb_ffflogog_whatermark_cc.jpg',
 'variant': None}
WARNING:scrapy.core.scraper:Dropped: 
{'deck': 'Reward',
 'image': '/cache/Ally-and-Villain-Packs/Wave-1/Chewbacca/Reward%20Cards/back_275_thumb_ffflogog_whatermark_cc.jpg',


'''