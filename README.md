# DVD Rental Manager

A command-line DVD rental application built with Python and MySQL. It handles
inventory, members, checkouts, reservations, ratings, and recommendations.

> Built for a university Introduction to Databases course (Seoul National University, 2026).

## Features

- **Inventory & members**: add / remove DVDs and users, with input validation
  (title/director length, age limits, uniqueness on title + director)
- **Checkout & reservations**: stock tracking, max 3 combined loans/reservations
  per user, age-restricted titles, one reservation per DVD
- **Overdue penalty system**: <explain briefly how penalty points and temporary
  borrowing restrictions work>
- **Return & rate**: ratings (1–5) update average scores; a returned DVD is
  automatically checked out to the waiting reservation holder
- **Search**: case-insensitive title search
- **Recommendations**:
  - Popularity-based: highest average rating and most rentals among unrated titles
  - <Optional> User-based collaborative filtering using cosine similarity
    over a user–item rating matrix
- Persistent state across restarts; database reset from the menu

## Tech stack

Python 3.10+, MySQL, `mysql-connector-python`, NumPy / pandas

## Database schema

<Insert an ER diagram or table list: DVDs, users, ratings, rentals,
reservations. Explain your key choices, e.g. how cumulative rental counts
and stock are stored, and what happens to related rows when a DVD or user is
deleted.>

## Getting started

```bash
git clone https://github.com/buugiiman/dvd-rental-app.git
cd dvd-rental-app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # fill in your MySQL credentials
export $(cat .env | xargs)
python run.py
```

Then choose `1` to initialize the database from a CSV of ratings.

## Example session

```
Select your action: 2
-----------------------------------------------------------------
id  title  director  age_limit  avg.rating  cumul_rent_cnt  stock  waiting
...
```
<paste real output from your own run>

## How the recommendation works

<2–3 paragraphs or a short list: temporary ratings for unrated items, cosine
similarity matrix, weighted-sum prediction. Include a small worked example in
your own numbers.>

## Design decisions & edge cases

- <e.g. how you made checkout + reservation updates atomic (transactions)>
- <e.g. how you handle ties in recommendations>
- <e.g. what happens when an auto-checkout fails after a return>

## Limitations

- <e.g. console UI only, single-user sessions, no concurrency handling>
  
