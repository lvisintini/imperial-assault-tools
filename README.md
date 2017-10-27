Install Opencv 3 as well -> [Instructions](http://www.pyimagesearch.com/2015/07/20/install-opencv-3-0-and-python-3-4-on-ubuntu/)

```
sudo add-apt-repository ppa:jonathonf/python-3.6
sudo apt update
sudo apt install python3.6
sudo apt install python3.6-dev virtualwrapper imagemagick wmctrl
sudo apt install libtiff5-dev libjpeg8-dev zlib1g-dev libfreetype6-dev liblcms2-dev libwebp-dev tcl8.6-dev tk8.6-dev python-tk
mkvirtualenv --python=/usr/bin/python3.6 imperial-assault-tools
pip install -r requirements.txt
scrapy shell "http://cards.boardwars.eu/index.php?album=Core-Box"
scrapy crawl imperial-assault-crawler
```
