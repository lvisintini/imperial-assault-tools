import scrapy


class ImperialAssaultCrawler(scrapy.Spider):
    name = 'imperial-assault-crawler'
    start_urls = ['http://cards.boardwars.eu/']

    def parse(self, response):
        [album.css('img ::attr(src)').extract_first() for album in response.css('div.album')]
        [album.css('a ::text').extract_first() for album in response.css('div.album')]
        [album.css('small ::text').extract_first() for album in response.css('div.album')]
        [image.css('img ::attr(src)').extract_first() for image in response.css('div.image')]

        for next_page in response.css('div.album > a'):
            yield response.follow(next_page, self.parse)
