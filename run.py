import csv
import math
import os
import numpy as np
from mysql.connector import connect

def get_connection():
    """Create a MySQL connection from environment variables."""

    try:
        return mysql.connector.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "3306")),
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            database=os.environ["DB_NAME"],
            charset="utf8",
        )
    except KeyError as e:
        raise SystemExit(f"Missing environment variable: {e}. See .env.example")

def run(func):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        result = func(cursor)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


DATA_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sample_data.csv')

MAX_BORROW = 3
INITIAL_STOCK = 2
PENALTY_THRESHOLD = 5
PENALTY_ATTEMPTS = 2

SET_TO_INITIAL_STATE = [
    '''
    CREATE TABLE IF NOT EXISTS dvd (
        d_id            INT          NOT NULL AUTO_INCREMENT,
        title           VARCHAR(100) NOT NULL,
        director        VARCHAR(100) NOT NULL,
        age_limit       INT          NOT NULL,
        stock           INT          NOT NULL DEFAULT 2,
        cumul_rent_cnt  INT          NOT NULL DEFAULT 0,
        PRIMARY KEY (d_id),
        UNIQUE KEY uq_dvd_title_director (title, director)
    ) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
    ''',
    '''
    CREATE TABLE IF NOT EXISTS user (
        u_id            INT          NOT NULL AUTO_INCREMENT,
        name            VARCHAR(100) NOT NULL,
        age             INT          NOT NULL,
        overdue         INT          NOT NULL DEFAULT 0,
        penalty_left    INT          NOT NULL DEFAULT 0,
        cumul_rent_cnt  INT          NOT NULL DEFAULT 0,
        PRIMARY KEY (u_id)
    ) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
    ''',
    '''
    CREATE TABLE IF NOT EXISTS rating (
        d_id    INT NOT NULL,
        u_id    INT NOT NULL,
        rating  INT NOT NULL,
        PRIMARY KEY (d_id, u_id),
        FOREIGN KEY (d_id) REFERENCES dvd (d_id)  ON DELETE CASCADE,
        FOREIGN KEY (u_id) REFERENCES user (u_id) ON DELETE CASCADE
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS borrowing (
        d_id    INT NOT NULL,
        u_id    INT NOT NULL,
        PRIMARY KEY (d_id, u_id),
        FOREIGN KEY (d_id) REFERENCES dvd (d_id)  ON DELETE CASCADE,
        FOREIGN KEY (u_id) REFERENCES user (u_id) ON DELETE CASCADE
    )
    ''',
    '''
    CREATE TABLE IF NOT EXISTS reservation (
        d_id    INT NOT NULL,
        u_id    INT NOT NULL,
        PRIMARY KEY (d_id),
        FOREIGN KEY (d_id) REFERENCES dvd (d_id)  ON DELETE CASCADE,
        FOREIGN KEY (u_id) REFERENCES user (u_id) ON DELETE CASCADE
    )
    ''',
]

def load_csv_rows():
    #"returns list of dicts"
    with open(DATA_CSV, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def fmt_rating(value, ndigits=1):
    if value is None:
        return 'None'
    
    value = float(value)
    factor = 10 ** ndigits
    rounded = math.floor(value * factor + 0.5) / factor

    if rounded == int(rounded):
        return str(int(rounded))
    # strip trailing zeros (e.g. 2.50 -> 2.5)
    text = f'{rounded:.{ndigits}f}'.rstrip('0').rstrip('.')
    return text

def initialize_database():
    def _impl(cursor):
        for statement in SET_TO_INITIAL_STATE:
            cursor.execute(statement)

        cursor.execute('SELECT COUNT(*) FROM dvd')
        dvd_cnt = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM user')
        user_cnt = cursor.fetchone()[0]
        if dvd_cnt == 0 and user_cnt == 0:
            rows = load_csv_rows()

            dvds = {}        # d_id -> (title, director, age_limit)
            users = {}       # u_id -> (name, age)
            ratings = {}     # (d_id, u_id) -> rating  (last record wins)
            dvd_rents = {}   # d_id -> number of past rentals (rating records)
            user_rents = {}  # u_id -> number of past rentals (rating records)

            for row in rows:
                d_id = int(row['d_id'])
                u_id = int(row['u_id'])
                dvds[d_id] = (row['d_title'], row['d_name'],
                                int(row['age_limit']))
                users[u_id] = (row['u_name'], int(row['u_age']))
                ratings[(d_id, u_id)] = int(row['rating'])
                dvd_rents[d_id] = dvd_rents.get(d_id, 0) + 1
                user_rents[u_id] = user_rents.get(u_id, 0) + 1

            cursor.executemany(
                'INSERT INTO dvd (d_id, title, director, age_limit, stock,'
                ' cumul_rent_cnt) VALUES (%s, %s, %s, %s, %s, %s)',
                [(d_id, t, d, a, INITIAL_STOCK, dvd_rents[d_id])
                    for d_id, (t, d, a) in sorted(dvds.items())])
            cursor.executemany(
                'INSERT INTO user (u_id, name, age, cumul_rent_cnt)'
                ' VALUES (%s, %s, %s, %s)',
                [(u_id, n, a, user_rents[u_id])
                    for u_id, (n, a) in sorted(users.items())])
            cursor.executemany(
                'INSERT INTO rating (d_id, u_id, rating) VALUES (%s, %s, %s)',
                [(d, u, r) for (d, u), r in sorted(ratings.items())])

    run(_impl)
    print('Database successfully initialized')
    
def reset():
    answer = input("All tables and data will be reset. Continue? (y/n): ")

    if answer.strip().lower() != 'y':
        return

    def _impl(cursor):
        cursor.execute('SET FOREIGN_KEY_CHECKS = 0')
        for table in ('reservation', 'borrowing', 'rating', 'dvd', 'user'):
            cursor.execute(f"DROP TABLE IF EXISTS {table}")

        cursor.execute('SET FOREIGN_KEY_CHECKS = 1')
    
    run(_impl)
    initialize_database()

def print_table(headers, rows):
    str_rows = [[str(c) for c in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in str_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    total = sum(widths) + 2 * (len(widths) - 1)
    line = '-' * max(80, total)
    print(line)
    print('  '.join(h.ljust(widths[i]) for i, h in enumerate(headers)).rstrip())
    print(line)
    for row in str_rows:
        print('  '.join(c.ljust(widths[i]) for i, c in enumerate(row)).rstrip())
    print(line)

def print_DVDs():
    def _impl(cursor):
        cursor.execute('''SELECT d.d_id, d.title, d.director, d.age_limit,
                   (SELECT AVG(r.rating) FROM rating r WHERE r.d_id = d.d_id),
                   d.cumul_rent_cnt, d.stock,
                   (SELECT COUNT(*) FROM reservation v WHERE v.d_id = d.d_id)
            FROM dvd d
            ORDER BY d.d_id ASC''')
        return cursor.fetchall()
    
    rows = run(_impl)
    table = [[d_id, title, director, age_limit, fmt_rating(avg),
              cumul, stock, waiting]
             for d_id, title, director, age_limit, avg, cumul, stock, waiting
             in rows]
    print_table(['id', 'title', 'director', 'age_limit', 'avg.rating',
                 'cumul_rent_cnt', 'stock', 'waiting'], table)

def print_users():
    def _impl(cursor):
        cursor.execute('''
            SELECT u.u_id, u.name, u.age,
                    (SELECT AVG(r.rating) FROM rating r WHERE r.u_id = u.u_id),
                    u.cumul_rent_cnt
            FROM user u
            ORDER BY u.u_id ASC''')
        return cursor.fetchall()

    rows = run(_impl)
    table = [[u_id, name, age, fmt_rating(avg), cumul]
             for u_id, name, age, avg, cumul in rows]
    print_table(['id', 'name', 'age', 'avg.rating', 'cumul_rent_cnt'], table)

def parse_int(str_int):
    try:
        return int(str(str_int).strip())
    except:
        return None

def insert_DVD():
    title = input('DVD title: ')
    director = input('DVD director: ')
    age_limit = input("Age limit: ")

    if not(1 <= len(title) <= 50):
        print('Title length should range from 1 to 50 characters')
        return
    
    if not (1 <= len(director) <= 30):
        print('Director length should range from 1 to 30 characters')
        return
    
    age_limit_int = parse_int(age_limit)
    if age_limit_int is None or not (0 <= age_limit_int <= 19):
        print("Age limit should be an integer from 0 to 19")
        return

    def _impl(cursor):
        cursor.execute(
            'SELECT 1 FROM dvd WHERE title = %s AND director = %s',
            (title, director))
        if cursor.fetchone():
            print(f'DVD ({title}, {director}) already exists')
            return
        cursor.execute(
            'INSERT INTO dvd (title, director, age_limit, stock)'
            ' VALUES (%s, %s, %s, %s)',
            (title, director, age_limit, INITIAL_STOCK))
        print('DVD successfully inserted')

    run(_impl)

def find_dvd(cursor, d_id):
    cursor.execute(
        'SELECT d_id, title, director, age_limit, stock, cumul_rent_cnt '
        'FROM dvd WHERE d_id = %s', (d_id,))
    return cursor.fetchone()

def remove_DVD():
    DVD_id = input('DVD ID: ')
    d_id = parse_int(DVD_id)

    def _impl(cursor):
        if d_id is None or find_dvd(cursor, d_id) is None:
            print(f"DVD {DVD_id.strip()} does not exist")
            return

        cursor.execute('SELECT 1 FROM borrowing WHERE d_id = %s LIMIT 1', (d_id,))
        if cursor.fetchone():
            print('Cannot delete a DVD that is currently borrowed')
            return
        
        cursor.execute('DELETE FROM dvd WHERE d_id = %s', (d_id,))
        print('DVD successfully removed')
    
    run(_impl)

def insert_user():
    name = input('User name: ')
    age = input('User age: ')

    if not (1 <= len(name) <= 30):
        print('Username length should range from 1 to 30 characters')
        return
    
    age = parse_int(age)

    if age is None or age <= 0:
        print('Age should be a positive integer')
        return

    def _impl(cursor):
        cursor.execute('INSERT INTO user (name, age) VALUES (%s, %s)',
                        (name, age))
        print('One user successfully inserted')

    run(_impl)

def find_user(cursor, user_id):
    cursor.execute(
        'SELECT u_id, name, age, overdue, penalty_left, cumul_rent_cnt '
        'FROM user WHERE u_id = %s', (user_id,))
    return cursor.fetchone()

def remove_user():
    user_id = input('User ID: ')
    user_id_int = parse_int(user_id)

    def _impl(cursor):
        if user_id_int is None or find_user(cursor, user_id_int) is None:
            print(f'User {user_id.strip()} does not exist')
            return
        cursor.execute('SELECT 1 FROM borrowing WHERE u_id = %s LIMIT 1', (user_id_int,))
        if cursor.fetchone():
            print('Cannot delete a user with borrowed DVDs')
            return
        # ratings / reservations are removed by ON DELETE CASCADE
        cursor.execute('DELETE FROM user WHERE u_id = %s', (user_id_int,))
        print('One user successfully removed')

    run(_impl)

def borrow_count(cursor, u_id):
    cursor.execute('SELECT COUNT(*) FROM borrowing WHERE u_id = %s', (u_id,))
    return cursor.fetchone()[0]

def reservation_count(cursor, u_id):
    cursor.execute('SELECT COUNT(*) FROM reservation WHERE u_id = %s', (u_id,))
    return cursor.fetchone()[0]

def get_reservation(cursor, d_id):
    cursor.execute('SELECT u_id FROM reservation WHERE d_id = %s', (d_id,))
    row = cursor.fetchone()
    return row[0] if row else None

def checkout_DVD():
    DVD_id = input('DVD ID: ')
    d_id = parse_int(DVD_id)

    def _find(cursor):
        if d_id is None:
            return None
        return find_dvd(cursor, d_id)

    dvd = run(_find)
    if dvd is None:
        print(f'DVD {DVD_id.strip()} does not exist')
        return
    _, _, _, age_limit, stock, _ = dvd

    if stock <= 0:
        answer = input('Reserve? (y/n): ')
        if answer.strip().lower() != 'y':
            return
        user_id = input('User ID: ')
        u_id = parse_int(user_id)

        def _reserve(cursor):
            user = None if u_id is None else find_user(cursor, u_id)
            if user is None:
                print(f'User {user_id.strip()} does not exist')
                return
            _, _, age, _, penalty_left, _ = user
            if age < age_limit:
                print(f'User {u_id} does not meet the age limit for this DVD')
                return
            if penalty_left > 0:
                print('Cannot make a reservation while under penalty.')
                return
            if borrow_count(cursor, u_id) + reservation_count(cursor, u_id) \
                    >= MAX_BORROW:
                print('Cannot make a reservation. The combined limit of '
                        'rentals and reservations is 3.')
                return
            if get_reservation(cursor, d_id) is not None:
                print('This DVD already has a reservation')
                return
            cursor.execute(
                'INSERT INTO reservation (d_id, u_id) VALUES (%s, %s)',
                (d_id, u_id))
            print('DVD reservation successfully registered')

        run(_reserve)
        return
    
    user_id = input('User ID: ')
    u_id = parse_int(user_id)

    def _rent(cursor):
        user = None if u_id is None else find_user(cursor, u_id)
        if user is None:
            print(f'User {user_id.strip()} does not exist')
            return
        _, _, age, _, _, _ = user
        if borrow_count(cursor, u_id) >= MAX_BORROW:
            print(f'User {u_id} exceeded the maximum borrowing limit')
            return
        if age < age_limit:
            print(f'User {u_id} does not meet the age limit for this DVD')
            return

        # This is a legitimate borrow attempt: every user currently
        # borrowing this DVD gets +1 overdue score.
        cursor.execute(
            'UPDATE user SET overdue = overdue + 1 WHERE u_id IN '
            '(SELECT u_id FROM borrowing WHERE d_id = %s)', (d_id,))
        # Users whose overdue score just reached the threshold become
        # restricted for the next PENALTY_ATTEMPTS legitimate attempts.
        cursor.execute(
            'UPDATE user SET penalty_left = %s '
            'WHERE overdue >= %s AND penalty_left = 0',
            (PENALTY_ATTEMPTS, PENALTY_THRESHOLD))

        # Penalty check on the requesting user (re-read, it may have changed).
        _, _, _, _, penalty_left, _ = find_user(cursor, u_id)
        if penalty_left > 0:
            penalty_left -= 1
            if penalty_left == 0:
                # Restriction is lifted; overdue score resets.
                cursor.execute(
                    'UPDATE user SET penalty_left = 0, overdue = 0 '
                    'WHERE u_id = %s', (u_id,))
            else:
                cursor.execute(
                    'UPDATE user SET penalty_left = %s WHERE u_id = %s',
                    (penalty_left, u_id))
            print(f'User {u_id} is currently restricted from borrowing DVDs '
                    f'({penalty_left} attempts left)')
            return

        cursor.execute(
            'INSERT INTO borrowing (d_id, u_id) VALUES (%s, %s)',
            (d_id, u_id))
        cursor.execute(
            'UPDATE dvd SET stock = stock - 1, '
            'cumul_rent_cnt = cumul_rent_cnt + 1 WHERE d_id = %s', (d_id,))
        cursor.execute(
            'UPDATE user SET cumul_rent_cnt = cumul_rent_cnt + 1 '
            'WHERE u_id = %s', (u_id,))
        print('DVD successfully checked out')
    
    run(_rent)

def return_and_rate_DVD():
    DVD_id = input('DVD ID: ')
    user_id = input('User ID: ')
    rating = input('Ratings (1~5): ')

    d_id = parse_int(DVD_id)
    u_id = parse_int(user_id)
    r_num = parse_int(rating)

    def _impl(cursor):
        if d_id is None or find_dvd(cursor, d_id) is None:
            print(f'DVD {DVD_id.strip()} does not exist')
            return
        if u_id is None or find_user(cursor, u_id) is None:
            print(f'User {user_id.strip()} does not exist')
            return
        if r_num is None or not (1 <= r_num <= 5):
            print('Rating should be an integer from 1 to 5')
            return
        cursor.execute(
            'SELECT 1 FROM borrowing WHERE d_id = %s AND u_id = %s',
            (d_id, u_id))
        if cursor.fetchone() is None:
            print('Cannot return and rate a DVD that is not currently '
                    'borrowed for this user')
            return

        cursor.execute('DELETE FROM borrowing WHERE d_id = %s AND u_id = %s',
                        (d_id, u_id))
        cursor.execute(
            'INSERT INTO rating (d_id, u_id, rating) VALUES (%s, %s, %s) '
            'ON DUPLICATE KEY UPDATE rating = VALUES(rating)',
            (d_id, u_id, r_num))
        print('DVD successfully returned and rated')

        # ----------------- automatic checkout for the reserver --------------
        reserver = get_reservation(cursor, d_id)
        if reserver is None:
            cursor.execute('UPDATE dvd SET stock = stock + 1 WHERE d_id = %s',
                            (d_id,))
            return

        _, _, _, _, penalty_left, _ = find_user(cursor, reserver)
        can_borrow = (borrow_count(cursor, reserver) < MAX_BORROW
                        and penalty_left == 0)
        cursor.execute('DELETE FROM reservation WHERE d_id = %s', (d_id,))
        if can_borrow:
            # The returned copy is handed directly to the reserver,
            # so the stock does not change.
            cursor.execute(
                'INSERT INTO borrowing (d_id, u_id) VALUES (%s, %s)',
                (d_id, reserver))
            cursor.execute(
                'UPDATE dvd SET cumul_rent_cnt = cumul_rent_cnt + 1 '
                'WHERE d_id = %s', (d_id,))
            cursor.execute(
                'UPDATE user SET cumul_rent_cnt = cumul_rent_cnt + 1 '
                'WHERE u_id = %s', (reserver,))
            print(f'DVD {d_id} has been automatically checked out for '
                    f'User {reserver}')
        else:
            cursor.execute('UPDATE dvd SET stock = stock + 1 WHERE d_id = %s',
                            (d_id,))

    run(_impl)

def cancel_reservation():
    DVD_id = input('DVD ID: ')
    d_id = parse_int(DVD_id)

    def _impl(cursor):
        if d_id is None or find_dvd(cursor, d_id) is None:
            print(f'DVD {DVD_id.strip()} does not exist')
            return
        if get_reservation(cursor, d_id) is None:
            print(f'Reservation for DVD {d_id} does not exist.')
            return
        cursor.execute('DELETE FROM reservation WHERE d_id = %s', (d_id,))
        print(f'Reservation for DVD {d_id} successfully cancelled')
    
    run(_impl)

def print_borrowing_status_for_user():
    user_id = input('User ID: ')
    u_id = parse_int(user_id)

    def _impl(cursor):
        if u_id is None or find_user(cursor, u_id) is None:
            print(f'User {user_id.strip()} does not exist')
            return None
        cursor.execute('''
            SELECT d.d_id, d.title, d.director, d.age_limit,
                (SELECT AVG(r.rating) FROM rating r WHERE r.d_id = d.d_id)
            FROM borrowing b JOIN dvd d ON b.d_id = d.d_id
            WHERE b.u_id = %s
            ORDER BY d.d_id ASC
        ''', (u_id,))
        return cursor.fetchall()
    
    rows = run(_impl)
    if rows is None:
        return
    table = [[d_id, title, director, age_limit, fmt_rating(avg)]
             for d_id, title, director, age_limit, avg in rows]
    print_table(['id', 'title', 'director', 'age_limit', 'avg.rating'], table)


def search():
    query = input('Query: ')

    def _impl(cursor):
        # Escape LIKE wildcards
        escaped = (query.replace('\\', '\\\\')
                        .replace('%', '\\%')
                        .replace('_', '\\_'))
        cursor.execute('''
            SELECT d.d_id, d.title, d.director, d.age_limit,
                    (SELECT AVG(r.rating) FROM rating r WHERE r.d_id = d.d_id),
                    d.stock,
                    (SELECT COUNT(*) FROM reservation v WHERE v.d_id = d.d_id)
            FROM dvd d
            WHERE LOWER(d.title) LIKE LOWER(%s)
            ORDER BY d.d_id ASC
        ''', (f'%{escaped}%',))
        return cursor.fetchall()

    rows = run(_impl)
    if not rows:
        print('Cannot find any matching results')
        return
    table = [[d_id, title, director, age_limit, fmt_rating(avg), stock,
              waiting]
             for d_id, title, director, age_limit, avg, stock, waiting in rows]
    print_table(['id', 'title', 'director', 'age_limit', 'avg.rating', 'stock', 'waiting'], table)

def block(label, headers, row):
    widths = [max(len(h), len(str(v))) for h, v in zip(headers, row)]
    total = sum(widths) + 2 * (len(widths) - 1)
    line = '-' * max(80, total)
    print(line)
    print(label)
    print(line)
    print('  '.join(h.ljust(widths[i]) for i, h in enumerate(headers)).rstrip())
    print(line)
    print('  '.join(str(v).ljust(widths[i]) for i, v in enumerate(row)).rstrip())

def recommend_popularity():
    user_id = input('User ID: ')
    u_id = parse_int(user_id)

    def _impl(cursor):
        user = None if u_id is None else find_user(cursor, u_id)
        if user is None:
            print(f'User {user_id.strip()} does not exist')
            return None
        _, _, age, _, _, _ = user
        # Candidates: DVDs the user has not rated, within the age limit.
        cursor.execute('''
            SELECT d.d_id, d.title, d.director, d.age_limit,
                    (SELECT AVG(r.rating) FROM rating r WHERE r.d_id = d.d_id),
                    d.cumul_rent_cnt, d.stock
            FROM dvd d
            WHERE d.age_limit <= %s
                AND NOT EXISTS (SELECT 1 FROM rating r
                                WHERE r.d_id = d.d_id AND r.u_id = %s)
            ORDER BY d.d_id ASC
        ''', (age, u_id))
        return cursor.fetchall()
    
    candidates = run(_impl)

    if candidates is None:
        return
    if not candidates:
        print('No DVD can be recommended')
        return

    best_rated = max(candidates, key=lambda c: (float(c[4]) if c[4] is not None else -1.0, -c[0]))
    
    best_popular = max(candidates, key=lambda c: (c[5], -c[0]))

    d_id, title, director, age_limit, avg, _, stock = best_rated
    block('Rating-based', ['id', 'title', 'director', 'age_limit', 'avg.rating', 'stock'], [d_id, title, director, age_limit, fmt_rating(avg), stock])

    d_id, title, director, age_limit, _, cumul, stock = best_popular
    block('Popularity-based', ['id', 'title', 'director', 'age_limit', 'cumul_rent_cnt', 'stock'], [d_id, title, director, age_limit, cumul, stock])

    print('-' * 80)

def avg_rating_of_dvd(cursor, d_id):
    cursor.execute('SELECT AVG(rating) FROM rating WHERE d_id = %s', (d_id,))
    return cursor.fetchone()[0]

def recommend_user_based():
    user_id = input('User ID: ')
    u_id = parse_int(user_id)

    def _impl(cursor):
        user = None if u_id is None else find_user(cursor, u_id)
        if user is None:
            print(f'User {user_id.strip()} does not exist')
            return None
        _, _, age, _, _, _ = user

        cursor.execute('SELECT u_id FROM user ORDER BY u_id ASC')
        user_ids = [row[0] for row in cursor.fetchall()]
        cursor.execute('SELECT d_id, title, director, age_limit FROM dvd '
                        'ORDER BY d_id ASC')
        dvds = cursor.fetchall()
        cursor.execute('SELECT d_id, u_id, rating FROM rating')
        ratings = cursor.fetchall()
        return age, user_ids, dvds, ratings

    data = run(_impl)
    if data is None:
        return
    age, user_ids, dvds, rating_rows = data

    dvd_ids = [d[0] for d in dvds]
    u_index = {u: i for i, u in enumerate(user_ids)}
    d_index = {d: j for j, d in enumerate(dvd_ids)}
    n, m = len(user_ids), len(dvd_ids)

    # user-item matrix
    matrix = np.full((n, m), np.nan)
    for d, u, r in rating_rows:
        matrix[u_index[u], d_index[d]] = float(r)
    rated_mask = ~np.isnan(matrix)

    # candidates: not rated by the target user and within the age limit.
    target = u_index[u_id]
    candidates = [j for j, (d_id, _, _, a_limit) in enumerate(dvds)
                  if a_limit <= age and not rated_mask[target, j]]
    if not candidates:
        print('No DVD can be recommended')
        return

    # fill missing entries with each user's mean rating (0 if none)
    filled = matrix.copy()
    for i in range(n):
        row_rated = rated_mask[i]
        mean = matrix[i, row_rated].mean() if row_rated.any() else 0.0
        filled[i, ~row_rated] = mean

    # cosine similarity between all users
    norms = np.linalg.norm(filled, axis=1)
    safe_norms = np.where(norms == 0, 1.0, norms)
    sim = (filled @ filled.T) / np.outer(safe_norms, safe_norms)
    sim[norms == 0, :] = 0.0
    sim[:, norms == 0] = 0.0

    # weighted-sum prediction over all other users
    weights = np.delete(sim[target], target)
    others = np.delete(filled, target, axis=0)
    denominator = weights.sum()
    if denominator != 0:
        predictions = (weights @ others) / denominator
    else:
        # no usable neighbours: fall back to the user's own temporary score.
        predictions = filled[target].copy()

    best_j = min(candidates,
                 key=lambda j: (-predictions[j], dvd_ids[j]))
    best_d_id, title, director, age_limit = dvds[best_j]

    def _avg(cursor):
        return avg_rating_of_dvd(cursor, best_d_id)

    avg = run(_avg)
    print_table(
        ['id', 'title', 'director', 'age_limit', 'avg.rating', 'exp.rating'],
        [[best_d_id, title, director, age_limit, fmt_rating(avg),
          fmt_rating(predictions[best_j], ndigits=2)]])

def main():
    while True:
        print('============================================================')
        print('1. initialize database')
        print('2. print all DVDs')
        print('3. print all users')
        print('4. insert a new DVD')
        print('5. remove a DVD')
        print('6. insert a new user')
        print('7. remove a user')
        print('8. check out a DVD')
        print('9. return and rate a DVD')
        print('10. cancel a reservation')
        print('11. print borrowing status of a user')
        print('12. search DVDs')
        print('13. search directors')
        print('14. recommend a DVD for a user using popularity-based method')
        print('15. recommend a DVD for a user using user-based collaborative filtering')
        print('16. exit')
        print('17. reset database')
        print('============================================================')
        menu = int(input('Select your action: '))

        if menu == 1:
            initialize_database()
        elif menu == 2:
            print_DVDs()
        elif menu == 3:
            print_users()
        elif menu == 4:
            insert_DVD()
        elif menu == 5:
            remove_DVD()
        elif menu == 6:
            insert_user()
        elif menu == 7:
            remove_user()
        elif menu == 8:
            checkout_DVD()
        elif menu == 9:
            return_and_rate_DVD()
        elif menu == 10:
            cancel_reservation()
        elif menu == 11:
            print_borrowing_status_for_user()
        elif menu == 12:
            search()
        elif menu == 13:
            search()
        elif menu == 14:
            recommend_popularity()
        elif menu == 15:
            recommend_user_based()
        elif menu == 16:
            print('Bye!')
            break
        elif menu == 17:
            reset()
        else:
            print('Invalid action')


if __name__ == "__main__":
    main()
