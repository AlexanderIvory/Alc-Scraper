General workflow:
  1. Use IdCheck.py to create a list of product ids (pid). At the end, change category_url to whatever category you want to scrape (e.g. https://www.danmurphys.com.au/beer/all)
  2. Use Scraper.py to extract the information of all pid in the imported csv (from IdCheck.py execution). At the end, make sure to change the name of the csv file and to name it appropriately.
  3. Use Analyser.py to sort and filter as need fit.
