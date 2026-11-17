# Supermarket Flyer to CSV

A simple data pipeline that turns weekly supermarket flyers into CSV files.

Every week supermarkets publish their offers as a PDF flyer. My pipeline downloads these flyers, reads the
products and prices, and saves them as one CSV file per week, so I can analyse them later.

Right now it works for **Kaufland** and **Netto**.

## How it works

I use PyMuPDF to read the text of the flyer. Each piece of text has a font, size and colour, and each store uses
them in its own way (for example, the price is the big text inside the red box). That's how the pipeline knows
what is a product name, a weight or a price.

I also tried Docling (an open-source AI tool for reading documents), but its results were not as accurate as
PyMuPDF, so I stayed with PyMuPDF.

Then every price is checked: price ÷ weight should match the unit price printed on the flyer. Offers that don't
match are set aside so I can check them myself.

## Run it

```bash
pip install -r requirements.txt
python run.py
```

The result is saved in `data/output/`, one file per week (for example `offers_2026-W47.csv`).
Weeks that are already done are skipped.

## Automation

GitHub Actions runs the pipeline every Sunday morning: it builds, tests, and then stores the new CSV file in
Backblaze B2.

## Next

Adding Lidl and ALDI Nord.