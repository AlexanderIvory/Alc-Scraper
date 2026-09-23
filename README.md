General workflow:
  1. Use **IdCheck.py** to create a list of product ids (pid) in a category
  2. Use **Scraper.py** to extract the information of all pid in the imported csv (from IdCheck.py execution)
  3. Use **Analyser.py** to sort and filter as need fit (from Scraper.py execution)

IdCheck.py
  1. Scroll to the bottom 
  2. ids var
    - **category_url** should be the category you want to scrape. E.g. https://www.danmurphys.com.au/beer/all
    - **max_pages** should be (#items in category / 25)+2. Divide by 25 for #items per page.
  3. write_ids var
    - **filename** is the name you want to save the pid as

Scraper.py
  1. Scroll to the bottom
  2. **PRODUCT_IDS** file input should be the file from IdCheck.py
  3. **rows** runs the scraper using PRODUCT_IDS and the number of workers. 4 workers is safest, 5 is faster but may cause errors. Ideal number of workers may change with device specifications.
  4. **write_csv** name input is the name of the file that outputs the product details for all pid.

Analyser.py
  1. **df** change the input to the product details you'd like. Recommended to be any output from Scraper.py.
  2. **print** can be changed to any sort or filter as you'd like
