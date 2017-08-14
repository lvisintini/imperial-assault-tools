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
            name = album.css('a ::text').extract_first().strip()
            yield items.CardBackItem(
                deck=name,
                variant=None if not name.startswith('Story') else self.get_section(response),
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
        section = self.get_section(response)
        breadcrumbs = self.get_breadcrumbs(response)

        for image in response.css('div.image'):
            source = breadcrumbs[-1] if section.startswith('Agenda') else breadcrumbs[-2]
            agenda = section if not section.startswith('Agenda') else '!!!!!!' + breadcrumbs[-1]

            yield items.AgendaCardItem(
                name=image.css('img ::attr(alt)').extract_first().strip(),
                agenda=agenda,
                image=image.css('img ::attr(src)').extract_first(),
                source=source
            )

    def parse_default_card(self, cls, response):
        breadcrumbs = self.get_breadcrumbs(response)
        for image in response.css('div.image'):
            yield cls(
                name=image.css('img ::attr(alt)').extract_first().strip(),
                image=image.css('img ::attr(src)').extract_first(),
                source=breadcrumbs[-1]
            )

    def parse_command_card(self, response):
        for item in self.parse_default_card(items.CommandCardItem, response):
            yield item

    def parse_reward(self, response):
        for item in self.parse_default_card(items.RewardItem, response):
            yield item

    def parse_companions(self, response):
        for item in self.parse_default_card(items.CompanionItem, response):
            yield item

    def parse_story_missions(self, response):
        for item in self.parse_default_card(items.StoryMissionCardItem, response):
            yield item

    def parse_supply_cards(self, response):
        for item in self.parse_default_card(items.SupplyCardItem, response):
            yield item

    def parse_tier_backs(self, response):
        for album in response.css('div.album'):
            yield items.CardBackItem(
                deck='Rebel Upgrade',
                variant=album.css('a ::text').extract_first().strip(),
                image=album.css('img ::attr(src)').extract_first().strip(),
            )
            yield response.follow(album.css('a::attr(href)').extract_first(), self.parse)

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
        elif section.startswith("Command"):
            return self.parse_command_card
        elif section.startswith("Reward"):
            return self.parse_reward
        elif section.startswith('Companion'):
            return self.parse_companions
        elif section.startswith('Suppl'):
            return self.parse_supply_cards
        elif section.startswith('Story'):
            return self.parse_story_missions
        elif 'upgrades'in section.lower():
            return self.parse_tier_backs
