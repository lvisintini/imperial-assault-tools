from crawler.utils import monkey_patch_logging

monkey_patch_logging()

BOT_NAME = 'crawler'

SPIDER_MODULES = ['crawler.spiders']
NEWSPIDER_MODULE = 'crawler.spiders'

ROBOTSTXT_OBEY = True

CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1

SPIDER_MIDDLEWARES = {
    "scrapy.spidermiddlewares.depth.DepthMiddleware": 500
}

DEPTH_PRIORITY = -1
SCHEDULER_DISK_QUEUE = 'scrapy.squeues.PickleFifoDiskQueue'
SCHEDULER_MEMORY_QUEUE = 'scrapy.squeues.FifoMemoryQueue'

ITEM_PIPELINES = {
    'crawler.pipelines.FixTyposAndNormalizeTextPipeline': 100,
    'crawler.pipelines.AddSourceIdsPipeline': 200,
    'crawler.pipelines.AddHeroIdsPipeline': 200,
    'crawler.pipelines.RemoveBacksPipeline': 200,
    'crawler.pipelines.FilterValidCardBacksPipeline': 300,
    'crawler.pipelines.ProcessAgendasPipeline': 300,
    'crawler.pipelines.ProcessSideMissionsPipeline': 300,
    'crawler.pipelines.ImageProcessingPipeline': 800,
    'crawler.pipelines.JsonWriterPipeline': 900,
}
