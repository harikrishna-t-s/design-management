import calendar
import configparser
import functools
import glob
import os
import re
import shutil
import sys
import traceback
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import mysql.connector
from mysql.connector import Error as MySQLError

try:
    import msvcrt
except ImportError:
    msvcrt = None


APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "db_config.ini")
ERROR_LOG_PATH = os.path.join(APP_DIR, "error_log.txt")

APP_TITLE = "Personal Design Management System"
BACKUP_MARKER = "-- Design Management System backup"
DATE_FORMAT = "%d-%m-%Y"

DEFAULT_CONFIG = {
    "host": "localhost",
    "port": "3306",
    "user": "root",
    "password": "",
    "database": "design_management",
}

WORK_STATUSES = ["Pending", "In Progress", "Completed"]
OTHER_TYPE_LABEL = "Other (type your own)"
WORK_TYPES = [
    "Logo",
    "Banner",
    "Poster",
    "Social Media Design",
    "Brochure",
    "Business Card",
    "Packaging",
]

SPECIAL_KEYS = {
    "H": "UP",
    "P": "DOWN",
    "K": "LEFT",
    "M": "RIGHT",
    "G": "HOME",
    "O": "END",
    "I": "PGUP",
    "Q": "PGDN",
    "S": "DELETE",
}

DOMAIN_PATTERN = re.compile(
    r"^(?=.{4,150}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$"
)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,64}$")
BACKUP_STATEMENT_PATTERN = re.compile(
    r"^(SET FOREIGN_KEY_CHECKS=[01];"
    r"|DROP TABLE IF EXISTS `(\w+)`;"
    r"|CREATE TABLE IF NOT EXISTS `(\w+)` "
    r"|INSERT INTO `(\w+)` )"
)

STATE = {"conn": None, "config": None, "dirty": False}

TABLE_DEFINITIONS = [
    (
        "companies",
        """
        CREATE TABLE IF NOT EXISTS `companies` (
            `company_id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
            `company_name` VARCHAR(150) NOT NULL,
            `owner_name` VARCHAR(100) NOT NULL,
            `contact_person` VARCHAR(100) NOT NULL,
            `approver_name` VARCHAR(100) NOT NULL,
            `approver_phone` VARCHAR(20) NULL,
            `approver_email` VARCHAR(120) NULL,
            `is_archived` TINYINT(1) NOT NULL DEFAULT 0,
            `archived_at` DATETIME NULL,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`company_id`),
            UNIQUE KEY `uq_company_name` (`company_name`),
            KEY `idx_company_owner` (`owner_name`),
            KEY `idx_company_archived` (`is_archived`),
            CONSTRAINT `chk_company_archived` CHECK (`is_archived` IN (0, 1))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        "company_domains",
        """
        CREATE TABLE IF NOT EXISTS `company_domains` (
            `domain_id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
            `company_id` INT UNSIGNED NOT NULL,
            `domain` VARCHAR(150) NOT NULL,
            PRIMARY KEY (`domain_id`),
            UNIQUE KEY `uq_domain` (`domain`),
            CONSTRAINT `fk_domain_company` FOREIGN KEY (`company_id`)
                REFERENCES `companies` (`company_id`)
                ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        "works",
        """
        CREATE TABLE IF NOT EXISTS `works` (
            `work_id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
            `company_id` INT UNSIGNED NOT NULL,
            `work_type` VARCHAR(60) NOT NULL,
            `colour_theme` VARCHAR(100) NOT NULL,
            `deadline` DATE NOT NULL,
            `estimated_hours` DECIMAL(6,2) NOT NULL,
            `description` TEXT NOT NULL,
            `status` ENUM('Pending','In Progress','Completed') NOT NULL DEFAULT 'Pending',
            `is_archived` TINYINT(1) NOT NULL DEFAULT 0,
            `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (`work_id`),
            KEY `idx_work_company` (`company_id`, `is_archived`),
            KEY `idx_work_deadline` (`deadline`),
            KEY `idx_work_type` (`work_type`),
            KEY `idx_work_status` (`status`),
            CONSTRAINT `fk_work_company` FOREIGN KEY (`company_id`)
                REFERENCES `companies` (`company_id`)
                ON DELETE RESTRICT ON UPDATE CASCADE,
            CONSTRAINT `chk_work_hours` CHECK (`estimated_hours` > 0),
            CONSTRAINT `chk_work_archived` CHECK (`is_archived` IN (0, 1))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        "archive_log",
        """
        CREATE TABLE IF NOT EXISTS `archive_log` (
            `log_id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
            `company_id` INT UNSIGNED NOT NULL,
            `action` ENUM('ARCHIVED','RESTORED') NOT NULL,
            `works_affected` INT UNSIGNED NOT NULL DEFAULT 0,
            `action_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (`log_id`),
            KEY `idx_log_company` (`company_id`, `action_time`),
            CONSTRAINT `fk_log_company` FOREIGN KEY (`company_id`)
                REFERENCES `companies` (`company_id`)
                ON DELETE RESTRICT ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
]
TABLE_NAMES = [name for name, _ in TABLE_DEFINITIONS]


def to_text(value):
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")
    return "" if value is None else str(value)


def log_error(context):
    try:
        with open(ERROR_LOG_PATH, "a", encoding="utf-8") as log_file:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_file.write(f"[{stamp}] {context}\n")
            log_file.write(traceback.format_exc() + "\n")
    except OSError:
        pass


def describe_db_error(error):
    code = getattr(error, "errno", None)
    messages = {
        1045: "Access denied. Check the MySQL user name and password in db_config.ini.",
        1044: "The MySQL user does not have permission to use this database.",
        1049: "The database does not exist.",
        1062: "That record already exists (duplicate value).",
        1451: "This record is still referenced by other records and cannot be removed.",
        1452: "The related company does not exist.",
        2002: "Cannot reach the MySQL server. Make sure MySQL is installed and running.",
        2003: "Cannot connect to the MySQL server. Make sure MySQL is running and the host and port are correct.",
        2005: "The MySQL host name could not be found. Check the host in db_config.ini.",
        2006: "The connection to the MySQL server was lost. Please try again.",
        2013: "The connection to the MySQL server was lost. Please try again.",
    }
    if code in messages:
        return messages[code]
    if code is None:
        return "A database problem occurred. Please try again."
    return f"A database problem occurred (error code {code})."


def safe_action(function):

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except MySQLError as error:
            log_error(f"Database error in {function.__name__}")
            show_error(describe_db_error(error))
        except OSError as error:
            log_error(f"File error in {function.__name__}")
            reason = error.strerror or "unknown problem"
            show_error(f"A file operation failed: {reason}.")
        except Exception:
            log_error(f"Unexpected error in {function.__name__}")
            show_error(
                "Something unexpected went wrong and the action was cancelled.\n"
                "Technical details were saved to error_log.txt."
            )
        return None

    return wrapper


def truncate(text, width):
    text = str(text)
    if len(text) <= width:
        return text
    return text[: max(0, width - 3)] + "..."


def like_pattern(text):
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def format_date(value):
    return value.strftime(DATE_FORMAT) if value else "-"


def format_hours(value):
    return format(Decimal(value).normalize(), "f")


def due_text(deadline, status):
    if status == "Completed":
        return "-"
    days = (deadline - date.today()).days
    if days < 0:
        return f"Overdue {-days}d"
    if days == 0:
        return "Today"
    return f"In {days}d"


def terminal_width():
    return max(60, shutil.get_terminal_size((100, 30)).columns - 1)


def terminal_height():
    return shutil.get_terminal_size((100, 30)).lines


def clear_screen():
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()


def print_header(title):
    clear_screen()
    line = "=" * min(terminal_width(), 70)
    print(line)
    print(f" {APP_TITLE}")
    print(line)
    print(f" {title}")
    print("-" * min(terminal_width(), 70))
    print()


def print_table(headers, rows):
    table = [[str(cell) for cell in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in table:
        for position, cell in enumerate(row):
            widths[position] = max(widths[position], len(cell))
    gap = 2
    available = terminal_width()
    while sum(widths) + gap * (len(widths) - 1) > available and max(widths) > 6:
        widths[widths.index(max(widths))] -= 1
    separator = " " * gap
    print(separator.join(truncate(h, w).ljust(w) for h, w in zip(headers, widths)))
    print(separator.join("-" * w for w in widths))
    for row in table:
        print(separator.join(truncate(c, w).ljust(w) for c, w in zip(row, widths)))


def show_result(title, message):
    print_header(title)
    print(message)
    pause()


def show_error(message):
    print_header("Error")
    print(message)
    pause()


def get_key():
    if msvcrt is None:
        raise RuntimeError("Keyboard navigation requires Windows.")
    char = msvcrt.getwch()
    if char in ("\x00", "\xe0"):
        return SPECIAL_KEYS.get(msvcrt.getwch(), "OTHER")
    if char in ("\r", "\n"):
        return "ENTER"
    if char == "\x1b":
        return "ESC"
    if char in ("\x08", "\x7f"):
        return "BACKSPACE"
    if char == "\x03":
        raise KeyboardInterrupt
    if char.isprintable():
        return char
    return "OTHER"


def pause(message="Press any key to continue..."):
    print()
    sys.stdout.write(message)
    sys.stdout.flush()
    get_key()
    print()


def read_line(prompt, default="", mask=False, max_length=300):
    shown = ""
    if default:
        shown = f" [{'*' * len(default) if mask else default}]"
    sys.stdout.write(f"{prompt}{shown}: ")
    sys.stdout.flush()
    buffer = []
    while True:
        key = get_key()
        if key == "ENTER":
            print()
            text = "".join(buffer)
            return text if text.strip() else default
        if key == "ESC":
            print()
            return None
        if key == "BACKSPACE":
            if buffer:
                buffer.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
        elif len(key) == 1 and len(buffer) < max_length:
            buffer.append(key)
            sys.stdout.write("*" if mask else key)
            sys.stdout.flush()


def menu(title, options, subtitle=None, start=0, footer=None):
    if not options:
        return None
    if footer is None:
        footer = "Up/Down: move    Enter: select    Esc: back"
    index = min(max(start, 0), len(options) - 1)
    top = 0
    sys.stdout.write("\x1b[?25l")
    try:
        while True:
            extra = subtitle.count("\n") + 3 if subtitle else 0
            page = max(5, terminal_height() - 12 - extra)
            if index < top:
                top = index
            if index >= top + page:
                top = index - page + 1
            print_header(title)
            if subtitle:
                print(subtitle)
                print()
            width = terminal_width() - 6
            if top > 0:
                print("   ... more above")
            for position in range(top, min(top + page, len(options))):
                label = truncate(options[position], width)
                if position == index:
                    print(f"\x1b[7m > {label} \x1b[0m")
                else:
                    print(f"   {label}")
            if top + page < len(options):
                print("   ... more below")
            print()
            print(footer)
            key = get_key()
            if key == "UP":
                index = (index - 1) % len(options)
            elif key == "DOWN":
                index = (index + 1) % len(options)
            elif key == "HOME":
                index = 0
            elif key == "END":
                index = len(options) - 1
            elif key == "PGUP":
                index = max(0, index - page)
            elif key == "PGDN":
                index = min(len(options) - 1, index + page)
            elif key == "ENTER":
                return index
            elif key == "ESC":
                return None
    finally:
        sys.stdout.write("\x1b[?25h")
        sys.stdout.flush()


def confirm(question, details=None, yes_label="Yes", no_label="No, cancel"):
    subtitle = question if not details else f"{question}\n\n{details}"
    choice = menu(
        "Confirmation",
        [no_label, yes_label],
        subtitle=subtitle,
        footer="Up/Down: move    Enter: select    Esc: cancel",
    )
    return choice == 1


def check_text(raw, label, max_length, required=True):
    value = " ".join(raw.split())
    if not value:
        if required:
            return None, f"{label} is required."
        return "", None
    if len(value) > max_length:
        return None, f"{label} must be at most {max_length} characters."
    return value, None


def check_person_name(raw, label):
    value, error = check_text(raw, label, 100)
    if error:
        return None, error
    allowed_extra = " .'-"
    if not value[0].isalpha() or not all(
        ch.isalpha() or ch in allowed_extra for ch in value
    ):
        return None, (
            f"{label} may contain only letters, spaces, dots, apostrophes "
            "and hyphens, and must start with a letter."
        )
    return value, None


def check_company_name(raw, exclude_id=None):
    value, error = check_text(raw, "Company name", 150)
    if error:
        return None, error
    existing = fetch_one(
        "SELECT company_id, is_archived FROM companies "
        "WHERE company_name = %s AND company_id <> %s",
        (value, exclude_id or 0),
    )
    if existing:
        if existing["is_archived"]:
            return None, (
                f"A company with this name is in the archive (ID {existing['company_id']}). "
                "Restore it from 'Retrieve Archived Company' instead."
            )
        return None, f"A company with this name already exists (ID {existing['company_id']})."
    return value, None


def normalise_domain(text):
    value = text.strip().lower()
    value = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", value)
    value = re.split(r"[/?#]", value)[0]
    if value.startswith("www."):
        value = value[4:]
    return value


def check_domains(raw, exclude_id=None):
    parts = [part for part in re.split(r"[,;\s]+", raw.strip()) if part]
    if not parts:
        return None, "At least one company domain is required."
    domains = []
    for part in parts:
        domain = normalise_domain(part)
        if not DOMAIN_PATTERN.match(domain):
            return None, f"'{part}' is not a valid domain. Example: example.com"
        if domain not in domains:
            domains.append(domain)
    for domain in domains:
        owner = fetch_one(
            "SELECT c.company_name FROM company_domains d "
            "JOIN companies c ON c.company_id = d.company_id "
            "WHERE d.domain = %s AND d.company_id <> %s",
            (domain, exclude_id or 0),
        )
        if owner:
            return None, f"The domain '{domain}' already belongs to '{owner['company_name']}'."
    return domains, None


def check_phone(raw, context):
    value = raw.strip()
    if value in ("", "-"):
        return "", None
    cleaned = re.sub(r"[\s\-().]", "", value)
    if not re.fullmatch(r"\+?[0-9]{7,15}", cleaned):
        return None, "Invalid phone number. Use 7 to 15 digits, optionally starting with +."
    return cleaned, None


def check_email(raw, context):
    value = raw.strip().lower()
    if value in ("", "-"):
        if not context.get("approver_phone"):
            return None, "Give at least a phone number or an email address."
        return "", None
    if len(value) > 120 or not EMAIL_PATTERN.match(value):
        return None, "Invalid email address. Example: name@example.com"
    return value, None


def parse_date(raw):
    text = raw.strip().replace("/", "-").replace(".", "-")
    try:
        parsed = datetime.strptime(text, DATE_FORMAT).date()
    except ValueError:
        return None
    if parsed.year < 2000 or parsed.year > 2100:
        return None
    return parsed


def check_date(raw, context):
    parsed = parse_date(raw)
    if parsed is None:
        return None, "Invalid date. Use DD-MM-YYYY, for example 25-12-2026."
    return parsed, None


def check_deadline(raw, context, existing_deadline=None):
    parsed = parse_date(raw)
    if parsed is None:
        return None, "Invalid date. Use DD-MM-YYYY, for example 25-12-2026."
    if (
        parsed < date.today()
        and context.get("status") != "Completed"
        and parsed != existing_deadline
    ):
        return None, (
            "The deadline cannot be in the past "
            f"(today is {format_date(date.today())})."
        )
    return parsed, None


def check_hours(raw, context):
    try:
        amount = Decimal(raw.strip())
    except InvalidOperation:
        return None, "Estimated time must be a number of hours, for example 6 or 7.5."
    if not amount.is_finite() or amount <= 0 or amount > Decimal("9999.99"):
        return None, "Estimated time must be above 0 and at most 9999.99 hours."
    return amount.quantize(Decimal("0.01")), None


def check_id(raw, label):
    value = raw.strip()
    if not (value.isascii() and value.isdigit()) or not 0 < int(value) <= 4294967295:
        return None, f"{label} must be a positive whole number."
    return int(value), None


def collect_fields(fields, defaults=None, initial=None):
    defaults = defaults or {}
    values = dict(initial or {})
    for key, prompt, validator in fields:
        default = defaults.get(key, "")
        while True:
            raw = read_line(prompt, default)
            if raw is None:
                return None
            value, error = validator(raw, values)
            if error:
                print(f"  ! {error}")
                continue
            values[key] = value
            break
    return values


def load_config():
    values = dict(DEFAULT_CONFIG)
    if not os.path.exists(CONFIG_PATH):
        return values, False
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(CONFIG_PATH, encoding="utf-8")
    if parser.has_section("mysql"):
        for key in values:
            if parser.has_option("mysql", key):
                values[key] = parser.get("mysql", key)
    return values, True


def save_config(values):
    parser = configparser.ConfigParser(interpolation=None)
    parser["mysql"] = {key: str(values[key]) for key in DEFAULT_CONFIG}
    with open(CONFIG_PATH, "w", encoding="utf-8") as config_file:
        parser.write(config_file)


def validate_config(values):
    if not values["host"].strip():
        return "The MySQL host must not be empty."
    if not values["port"].isascii() or not values["port"].isdigit() or not 0 < int(values["port"]) < 65536:
        return "The port must be a number between 1 and 65535."
    if not values["user"].strip():
        return "The MySQL user must not be empty."
    if not DATABASE_NAME_PATTERN.match(values["database"]):
        return "The database name may contain only letters, digits and underscores (max 64)."
    return None


def prompt_config(current):
    values = dict(current)
    while True:
        print_header("Database Connection Settings")
        print("Press Enter to keep the value in brackets. Press Esc to cancel.\n")
        answers = {}
        for key, label, mask in (
            ("host", "MySQL host", False),
            ("port", "MySQL port", False),
            ("user", "MySQL user", False),
            ("password", "MySQL password (Enter keeps current)", True),
            ("database", "Database name", False),
        ):
            answer = read_line(label, values[key], mask=mask)
            if answer is None:
                return None
            answers[key] = answer.strip() if key != "password" else answer
        error = validate_config(answers)
        if error:
            print(f"\n  ! {error}")
            pause()
            values = answers
            continue
        save_config(answers)
        return answers


def connect_to_mysql(values, use_database):
    options = {
        "host": values["host"],
        "port": int(values["port"]),
        "user": values["user"],
        "password": values["password"],
        "charset": "utf8mb4",
        "connection_timeout": 10,
        "autocommit": True,
    }
    if use_database:
        options["database"] = values["database"]
    return mysql.connector.connect(**options)


def initialize_database(values):
    db_name = values["database"]
    connection = connect_to_mysql(values, False)
    messages = []
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
            (db_name,),
        )
        if int(cursor.fetchone()[0]) == 0:
            cursor.execute(
                f"CREATE DATABASE `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            messages.append(f"Database '{db_name}' was created.")
        else:
            messages.append(f"Using existing database '{db_name}'.")
        cursor.execute(f"USE `{db_name}`")
        cursor.execute("SHOW TABLES")
        present = {to_text(row[0]).lower() for row in cursor.fetchall()}
        created = []
        for name, definition in TABLE_DEFINITIONS:
            if name not in present:
                cursor.execute(definition)
                created.append(name)
        if created:
            messages.append("Created missing tables: " + ", ".join(created) + ".")
        else:
            messages.append("All required tables are present.")
        cursor.close()
    finally:
        connection.close()
    return messages


def get_connection():
    connection = STATE["conn"]
    if connection is None:
        raise MySQLError(msg="Not connected", errno=2006)
    connection.ping(reconnect=True, attempts=3, delay=1)
    return connection


def fetch_all(sql, params=()):
    cursor = get_connection().cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()


def fetch_one(sql, params=()):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def transaction(work):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        connection.start_transaction()
        result = work(cursor)
        connection.commit()
        STATE["dirty"] = True
        return result
    except Exception:
        try:
            connection.rollback()
        except MySQLError:
            pass
        raise
    finally:
        cursor.close()


def execute(sql, params=()):

    def work(cursor):
        cursor.execute(sql, params)
        return cursor.lastrowid

    return transaction(work)


def find_companies(text="", archived=False, name_only=False):
    sql = (
        "SELECT c.*, (SELECT GROUP_CONCAT(d.domain ORDER BY d.domain SEPARATOR ', ') "
        "FROM company_domains d WHERE d.company_id = c.company_id) AS domains "
        "FROM companies c WHERE c.is_archived = %s"
    )
    params = [1 if archived else 0]
    if text:
        name_pattern = like_pattern(text)
        if name_only:
            sql += " AND c.company_name LIKE %s"
            params.append(name_pattern)
        else:
            domain_pattern = like_pattern(normalise_domain(text) or text)
            sql += (
                " AND (c.company_name LIKE %s OR c.owner_name LIKE %s OR EXISTS "
                "(SELECT 1 FROM company_domains d2 WHERE d2.company_id = c.company_id "
                "AND d2.domain LIKE %s))"
            )
            params.extend([name_pattern, name_pattern, domain_pattern])
    sql += " ORDER BY c.company_name"
    rows = fetch_all(sql, tuple(params))
    for row in rows:
        row["domains"] = to_text(row["domains"])
    return rows


def company_label(company):
    return (
        f"ID {company['company_id']} | {company['company_name']} | "
        f"Owner: {company['owner_name']} | {company['domains'] or '-'}"
    )


def format_company_details(company):
    lines = [
        f"Company ID       : {company['company_id']}",
        f"Company name     : {company['company_name']}",
        f"Owner            : {company['owner_name']}",
        f"Domain(s)        : {company['domains'] or '-'}",
        f"Contact person   : {company['contact_person']}",
        f"Final approval   : {company['approver_name']}",
        f"Approver phone   : {company['approver_phone'] or '-'}",
        f"Approver email   : {company['approver_email'] or '-'}",
    ]
    return "\n".join(lines)


def select_company(title, archived=False):
    print_header(title)
    if archived:
        print("Search archived companies by name (Enter = list all, Esc = cancel).\n")
        text = read_line("Company name")
    else:
        print("Search by company name, domain or owner (Enter = list all, Esc = cancel).\n")
        text = read_line("Search")
    if text is None:
        return None
    rows = find_companies(" ".join(text.split()), archived, name_only=archived)
    if not rows:
        print("\nNo matching companies found.")
        pause()
        return None
    choice = menu(
        title,
        [company_label(row) for row in rows],
        subtitle=f"{len(rows)} company record(s) found. Select one:",
    )
    return None if choice is None else rows[choice]


def company_fields(exclude_id=None):
    return [
        ("company_name", "Company name", lambda raw, ctx: check_company_name(raw, exclude_id)),
        ("owner_name", "Owner name", lambda raw, ctx: check_person_name(raw, "Owner name")),
        ("domains", "Company domain(s), comma separated", lambda raw, ctx: check_domains(raw, exclude_id)),
        ("contact_person", "Contact person name", lambda raw, ctx: check_person_name(raw, "Contact person name")),
        ("approver_name", "Final approval person name", lambda raw, ctx: check_person_name(raw, "Approval person name")),
        ("approver_phone", "Approval person phone (optional if email given)", check_phone),
        ("approver_email", "Approval person email (optional if phone given)", check_email),
    ]


@safe_action
def add_company():
    print_header("Add Company")
    print("Press Esc at any prompt to cancel.\n")
    values = collect_fields(company_fields())
    if values is None:
        show_result("Add Company", "Cancelled. Nothing was saved.")
        return
    preview = dict(values)
    preview["company_id"] = "(assigned on save)"
    preview["domains"] = ", ".join(values["domains"])
    if not confirm("Save this company?", format_company_details(preview), "Yes, save"):
        show_result("Add Company", "Cancelled. Nothing was saved.")
        return

    def work(cursor):
        cursor.execute(
            "INSERT INTO companies (company_name, owner_name, contact_person, "
            "approver_name, approver_phone, approver_email) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                values["company_name"],
                values["owner_name"],
                values["contact_person"],
                values["approver_name"],
                values["approver_phone"] or None,
                values["approver_email"] or None,
            ),
        )
        company_id = cursor.lastrowid
        for domain in values["domains"]:
            cursor.execute(
                "INSERT INTO company_domains (company_id, domain) VALUES (%s, %s)",
                (company_id, domain),
            )
        return company_id

    company_id = transaction(work)
    show_result("Add Company", f"Company saved. Its company ID is {company_id}.")


@safe_action
def update_company():
    company = select_company("Update Company")
    if company is None:
        return
    print_header(f"Update Company - ID {company['company_id']}")
    print("Enter keeps the current value. Type - to clear an optional value.")
    print("Press Esc to cancel.\n")
    defaults = {
        "company_name": company["company_name"],
        "owner_name": company["owner_name"],
        "domains": company["domains"],
        "contact_person": company["contact_person"],
        "approver_name": company["approver_name"],
        "approver_phone": company["approver_phone"] or "",
        "approver_email": company["approver_email"] or "",
    }
    values = collect_fields(company_fields(company["company_id"]), defaults)
    if values is None:
        show_result("Update Company", "Cancelled. No changes were made.")
        return
    old_domains = sorted(d.strip() for d in company["domains"].split(",") if d.strip())
    changed = (
        any(values[key] != defaults[key] for key in defaults if key != "domains")
        or sorted(values["domains"]) != old_domains
    )
    if not changed:
        show_result("Update Company", "Nothing was changed.")
        return
    preview = dict(values)
    preview["company_id"] = company["company_id"]
    preview["domains"] = ", ".join(values["domains"])
    if not confirm("Save these changes?", format_company_details(preview), "Yes, save changes"):
        show_result("Update Company", "Cancelled. No changes were made.")
        return

    def work(cursor):
        cursor.execute(
            "UPDATE companies SET company_name = %s, owner_name = %s, contact_person = %s, "
            "approver_name = %s, approver_phone = %s, approver_email = %s "
            "WHERE company_id = %s AND is_archived = 0",
            (
                values["company_name"],
                values["owner_name"],
                values["contact_person"],
                values["approver_name"],
                values["approver_phone"] or None,
                values["approver_email"] or None,
                company["company_id"],
            ),
        )
        cursor.execute(
            "DELETE FROM company_domains WHERE company_id = %s", (company["company_id"],)
        )
        for domain in values["domains"]:
            cursor.execute(
                "INSERT INTO company_domains (company_id, domain) VALUES (%s, %s)",
                (company["company_id"], domain),
            )

    transaction(work)
    show_result("Update Company", "Company updated.")


@safe_action
def search_company():
    return select_company("Search Company")


@safe_action
def display_companies():
    rows = find_companies()
    print_header("All Companies")
    if not rows:
        print("No companies have been added yet.")
    else:
        print_table(
            ["ID", "Company", "Owner", "Domain(s)", "Final approval person"],
            [
                [r["company_id"], r["company_name"], r["owner_name"], r["domains"], r["approver_name"]]
                for r in rows
            ],
        )
        print(f"\nTotal: {len(rows)} active company record(s).")
    pause()


@safe_action
def archive_company():
    company = select_company("Delete Company (Archive)")
    if company is None:
        return
    company_id = company["company_id"]
    total = fetch_one(
        "SELECT COUNT(*) AS total FROM works WHERE company_id = %s AND is_archived = 0",
        (company_id,),
    )["total"]
    details = (
        format_company_details(company)
        + f"\n\nIts {total} work record(s) will be kept and archived with it."
        + "\nYou can bring everything back with 'Retrieve Archived Company'."
    )
    if not confirm(
        f"Archive '{company['company_name']}'?", details, "Yes, archive this company"
    ):
        show_result("Delete Company", "Cancelled. The company was not archived.")
        return

    def work(cursor):
        cursor.execute(
            "UPDATE companies SET is_archived = 1, archived_at = NOW() "
            "WHERE company_id = %s AND is_archived = 0",
            (company_id,),
        )
        cursor.execute("UPDATE works SET is_archived = 1 WHERE company_id = %s", (company_id,))
        affected = cursor.rowcount
        cursor.execute(
            "INSERT INTO archive_log (company_id, action, works_affected) "
            "VALUES (%s, 'ARCHIVED', %s)",
            (company_id, affected),
        )

    transaction(work)
    show_result(
        "Delete Company",
        f"'{company['company_name']}' was archived together with its work records.",
    )


@safe_action
def restore_company():
    company = select_company("Retrieve Archived Company", archived=True)
    if company is None:
        return
    company_id = company["company_id"]
    total = fetch_one(
        "SELECT COUNT(*) AS total FROM works WHERE company_id = %s AND is_archived = 1",
        (company_id,),
    )["total"]
    details = format_company_details(company) + f"\n\n{total} archived work record(s) will be restored."
    if not confirm(
        f"Restore '{company['company_name']}'?", details, "Yes, restore this company"
    ):
        show_result("Retrieve Archived Company", "Cancelled. Nothing was restored.")
        return

    def work(cursor):
        cursor.execute(
            "UPDATE companies SET is_archived = 0, archived_at = NULL "
            "WHERE company_id = %s AND is_archived = 1",
            (company_id,),
        )
        cursor.execute("UPDATE works SET is_archived = 0 WHERE company_id = %s", (company_id,))
        affected = cursor.rowcount
        cursor.execute(
            "INSERT INTO archive_log (company_id, action, works_affected) "
            "VALUES (%s, 'RESTORED', %s)",
            (company_id, affected),
        )

    transaction(work)
    show_result(
        "Retrieve Archived Company",
        f"'{company['company_name']}' and its work records were restored.",
    )


def query_works(company_id=None, extra_where="", extra_params=(), text=""):
    sql = (
        "SELECT w.*, c.company_name FROM works w "
        "JOIN companies c ON c.company_id = w.company_id "
        "WHERE w.is_archived = 0 AND c.is_archived = 0"
    )
    params = []
    if company_id is not None:
        sql += " AND w.company_id = %s"
        params.append(company_id)
    if text:
        pattern = like_pattern(text)
        sql += (
            " AND (CAST(w.work_id AS CHAR) = %s OR w.work_type LIKE %s "
            "OR w.description LIKE %s)"
        )
        params.extend([text, pattern, pattern])
    sql += extra_where + " ORDER BY w.deadline, w.work_id"
    params.extend(extra_params)
    rows = fetch_all(sql, tuple(params))
    for row in rows:
        row["description"] = to_text(row["description"])
    return rows


def get_work(work_id, company_id):
    rows = query_works(company_id, " AND w.work_id = %s", (work_id,))
    return rows[0] if rows else None


def work_label(work):
    return (
        f"ID {work['work_id']} | {work['work_type']} | Due {format_date(work['deadline'])} "
        f"| {work['status']} | {work['description']}"
    )


def format_work_details(work):
    lines = [
        f"Work ID          : {work['work_id']}",
        f"Work type        : {work['work_type']}",
        f"Colour theme     : {work['colour_theme']}",
        f"Deadline         : {format_date(work['deadline'])}",
        f"Estimated time   : {format_hours(work['estimated_hours'])} hours",
        f"Status           : {work['status']}",
        f"Description      : {work['description']}",
    ]
    return "\n".join(lines)


def show_work_table(title, rows, with_company, note=""):
    print_header(title)
    if note:
        print(note)
        print()
    if not rows:
        print("No work records found.")
        pause()
        return
    headers = ["ID"] + (["Company"] if with_company else []) + [
        "Type", "Colour theme", "Deadline", "Due", "Hours", "Status", "Description",
    ]
    table = []
    for work in rows:
        line = [work["work_id"]]
        if with_company:
            line.append(work["company_name"])
        line += [
            work["work_type"],
            work["colour_theme"],
            format_date(work["deadline"]),
            due_text(work["deadline"], work["status"]),
            format_hours(work["estimated_hours"]),
            work["status"],
            work["description"],
        ]
        table.append(line)
    print_table(headers, table)
    counts = {status: sum(1 for r in rows if r["status"] == status) for status in WORK_STATUSES}
    print(
        f"\nTotal: {len(rows)} | Pending: {counts['Pending']} | "
        f"In Progress: {counts['In Progress']} | Completed: {counts['Completed']}"
    )
    pause()


def select_work(company, title):
    print_header(f"{title} - {company['company_name']}")
    print("Search by work ID, work type or description (Enter = list all, Esc = cancel).\n")
    text = read_line("Search")
    if text is None:
        return None
    rows = query_works(company["company_id"], text=" ".join(text.split()))
    if not rows:
        print("\nNo matching work records found.")
        pause()
        return None
    choice = menu(
        title,
        [work_label(row) for row in rows],
        subtitle=f"{len(rows)} work record(s) found. Select one:",
    )
    return None if choice is None else rows[choice]


def choose_work_type(current=None):
    options = list(WORK_TYPES) + [OTHER_TYPE_LABEL]
    if current:
        options.insert(0, f"Keep current ({current})")
    choice = menu("Select Work Type", options, subtitle="Choose the type of design work:")
    if choice is None:
        return None
    if current and choice == 0:
        return current
    if options[choice] != OTHER_TYPE_LABEL:
        return options[choice]
    print_header("Custom Work Type")
    while True:
        raw = read_line("Work type (Esc to cancel)")
        if raw is None:
            return None
        value, error = check_text(raw, "Work type", 60)
        if error:
            print(f"  ! {error}")
            continue
        return value


def choose_status(current="Pending"):
    start = WORK_STATUSES.index(current) if current in WORK_STATUSES else 0
    choice = menu("Select Work Status", WORK_STATUSES, subtitle="Choose the work status:", start=start)
    if choice is None:
        return None
    return WORK_STATUSES[choice]


def work_fields(existing_deadline=None):
    return [
        ("colour_theme", "Colour theme", lambda raw, ctx: check_text(raw, "Colour theme", 100)),
        ("deadline", "Assigned deadline (DD-MM-YYYY)", lambda raw, ctx: check_deadline(raw, ctx, existing_deadline)),
        ("estimated_hours", "Estimated completion time in hours", check_hours),
        ("description", "Work description", lambda raw, ctx: check_text(raw, "Work description", 1000)),
    ]


@safe_action
def add_work(company):
    work_type = choose_work_type()
    if work_type is None:
        show_result("Add Work", "Cancelled. Nothing was saved.")
        return
    status = choose_status("Pending")
    if status is None or status not in WORK_STATUSES:
        show_result("Add Work", "Cancelled. Nothing was saved.")
        return
    print_header(f"Add Work - {company['company_name']}")
    print(f"Work type : {work_type}")
    print(f"Status    : {status}")
    print("\nPress Esc at any prompt to cancel.\n")
    values = collect_fields(work_fields(), initial={"status": status})
    if values is None:
        show_result("Add Work", "Cancelled. Nothing was saved.")
        return
    preview = dict(values)
    preview["work_id"] = "(assigned on save)"
    preview["work_type"] = work_type
    if not confirm("Save this work record?", format_work_details(preview), "Yes, save"):
        show_result("Add Work", "Cancelled. Nothing was saved.")
        return
    work_id = execute(
        "INSERT INTO works (company_id, work_type, colour_theme, deadline, "
        "estimated_hours, description, status) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (
            company["company_id"],
            work_type,
            values["colour_theme"],
            values["deadline"],
            values["estimated_hours"],
            values["description"],
            status,
        ),
    )
    show_result("Add Work", f"Work saved. Its work ID is {work_id}.")


@safe_action
def update_work(company):
    work = select_work(company, "Update Work")
    if work is None:
        return
    work_type = choose_work_type(work["work_type"])
    if work_type is None:
        show_result("Update Work", "Cancelled. No changes were made.")
        return
    status = choose_status(work["status"])
    if status is None or status not in WORK_STATUSES:
        show_result("Update Work", "Cancelled. No changes were made.")
        return
    print_header(f"Update Work - ID {work['work_id']}")
    print(f"Work type : {work_type}")
    print(f"Status    : {status}")
    print("\nEnter keeps the current value. Press Esc to cancel.\n")
    defaults = {
        "colour_theme": work["colour_theme"],
        "deadline": format_date(work["deadline"]),
        "estimated_hours": format_hours(work["estimated_hours"]),
        "description": work["description"],
    }
    values = collect_fields(
        work_fields(work["deadline"]), defaults, initial={"status": status}
    )
    if values is None:
        show_result("Update Work", "Cancelled. No changes were made.")
        return
    changed = (
        work_type != work["work_type"]
        or status != work["status"]
        or values["colour_theme"] != work["colour_theme"]
        or values["deadline"] != work["deadline"]
        or values["estimated_hours"] != work["estimated_hours"]
        or values["description"] != work["description"]
    )
    if not changed:
        show_result("Update Work", "Nothing was changed.")
        return
    preview = dict(values)
    preview["work_id"] = work["work_id"]
    preview["work_type"] = work_type
    if not confirm("Save these changes?", format_work_details(preview), "Yes, save changes"):
        show_result("Update Work", "Cancelled. No changes were made.")
        return
    execute(
        "UPDATE works SET work_type = %s, colour_theme = %s, deadline = %s, "
        "estimated_hours = %s, description = %s, status = %s "
        "WHERE work_id = %s AND company_id = %s AND is_archived = 0",
        (
            work_type,
            values["colour_theme"],
            values["deadline"],
            values["estimated_hours"],
            values["description"],
            status,
            work["work_id"],
            company["company_id"],
        ),
    )
    show_result("Update Work", "Work record updated.")


def build_work_filter(choice):
    today = date.today()
    if choice == 0:
        raw = read_line("Work type to search for")
        if raw is None:
            return None
        value, error = check_text(raw, "Work type", 60)
        if error:
            show_error(error)
            return None
        return " AND w.work_type LIKE %s", (like_pattern(value),), f"work type contains '{value}'"
    if choice == 1:
        raw = read_line("Deadline date (DD-MM-YYYY)")
        if raw is None:
            return None
        parsed, error = check_date(raw, {})
        if error:
            show_error(error)
            return None
        return " AND w.deadline = %s", (parsed,), f"deadline is {format_date(parsed)}"
    if choice == 2:
        start_raw = read_line("From date (DD-MM-YYYY)")
        if start_raw is None:
            return None
        end_raw = read_line("To date (DD-MM-YYYY)")
        if end_raw is None:
            return None
        start, error = check_date(start_raw, {})
        end, error_end = check_date(end_raw, {})
        if error or error_end:
            show_error(error or error_end)
            return None
        if start > end:
            show_error("The 'From' date must not be after the 'To' date.")
            return None
        return (
            " AND w.deadline BETWEEN %s AND %s",
            (start, end),
            f"deadline from {format_date(start)} to {format_date(end)}",
        )
    if choice == 3:
        return (
            " AND w.deadline = %s AND w.status <> 'Completed'",
            (today,),
            f"not completed and due today ({format_date(today)})",
        )
    if choice == 4:
        end = today + timedelta(days=7)
        return (
            " AND w.deadline BETWEEN %s AND %s AND w.status <> 'Completed'",
            (today, end),
            f"not completed and due {format_date(today)} to {format_date(end)}",
        )
    if choice == 5:
        first = today.replace(day=1)
        last = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        return (
            " AND w.deadline BETWEEN %s AND %s",
            (first, last),
            f"deadline in {today.strftime('%B %Y')}",
        )
    if choice == 6:
        return (
            " AND w.deadline < %s AND w.status <> 'Completed'",
            (today,),
            "overdue and not completed",
        )
    status = choose_status("Pending")
    if status is None:
        return None
    return " AND w.status = %s", (status,), f"status is {status}"


@safe_action
def search_work(company):
    filters = [
        "Work type",
        "Exact deadline date",
        "Deadline between two dates",
        "Due today (not completed)",
        "Due in the next 7 days (not completed)",
        "Deadline this month (all statuses)",
        "Overdue (not completed)",
        "Work status",
    ]
    choice = menu("Search Work", filters, subtitle="Search by:")
    if choice is None:
        return
    scope = menu(
        "Search Work",
        [f"This company only ({company['company_name']})", "All active companies"],
        subtitle="Where should the search look?",
    )
    if scope is None:
        return
    print_header("Search Work")
    print("Press Esc to cancel.\n")
    built = build_work_filter(choice)
    if built is None:
        return
    condition, params, description = built
    company_id = company["company_id"] if scope == 0 else None
    rows = query_works(company_id, condition, params)
    show_work_table(
        "Search Results",
        rows,
        with_company=scope == 1,
        note=f"Search: {description}",
    )


@safe_action
def display_works(company):
    scope = menu(
        "Display Works",
        [f"This company's works ({company['company_name']})", "Works of all active companies"],
        subtitle="Which works do you want to see?",
    )
    if scope is None:
        return
    if scope == 0:
        rows = query_works(company["company_id"])
        show_work_table(f"Works - {company['company_name']}", rows, with_company=False)
    else:
        rows = query_works()
        show_work_table("Works - All Active Companies", rows, with_company=True)


@safe_action
def delete_work(company):
    print_header(f"Delete Work - {company['company_name']}")
    print("Press Esc to cancel.\n")
    raw = read_line("Work ID to delete")
    if raw is None:
        return
    work_id, error = check_id(raw, "Work ID")
    if error:
        show_error(error)
        return
    work = get_work(work_id, company["company_id"])
    if work is None:
        show_error(f"No work with ID {work_id} exists for this company.")
        return
    if not confirm(
        f"Permanently delete work ID {work_id}?",
        format_work_details(work) + "\n\nThis cannot be undone.",
        "Yes, delete this work",
    ):
        show_result("Delete Work", "Cancelled. The work record was not deleted.")
        return
    execute(
        "DELETE FROM works WHERE work_id = %s AND company_id = %s",
        (work_id, company["company_id"]),
    )
    show_result("Delete Work", f"Work ID {work_id} was deleted.")


def sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, Decimal)):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, datetime):
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S") + "'"
    if isinstance(value, date):
        return "'" + value.isoformat() + "'"
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex() if value else "''"
    text = str(value)
    for char, escaped in (
        ("\\", "\\\\"),
        ("'", "\\'"),
        ("\0", "\\0"),
        ("\n", "\\n"),
        ("\r", "\\r"),
        ("\x1a", "\\Z"),
    ):
        text = text.replace(char, escaped)
    return "'" + text + "'"


def write_backup(suffix=""):
    connection = get_connection()
    db_name = STATE["config"]["database"]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{db_name}_backup_{stamp}{suffix}"
    counter = 0
    while True:
        name = base + (f"_{counter}" if counter else "") + ".sql"
        path = os.path.join(APP_DIR, name)
        try:
            handle = open(path, "x", encoding="utf-8", newline="\n")
            break
        except FileExistsError:
            counter += 1
    cursor = connection.cursor()
    try:
        with handle:
            handle.write(f"{BACKUP_MARKER}\n")
            handle.write(f"-- Database: {db_name}\n")
            handle.write(f"-- Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            handle.write("SET FOREIGN_KEY_CHECKS=0;\n")
            for name, _ in reversed(TABLE_DEFINITIONS):
                handle.write(f"DROP TABLE IF EXISTS `{name}`;\n")
            for _, definition in TABLE_DEFINITIONS:
                handle.write(" ".join(definition.split()) + ";\n")
            for name, _ in TABLE_DEFINITIONS:
                cursor.execute(f"SELECT * FROM `{name}` ORDER BY 1")
                columns = ", ".join(f"`{column}`" for column in cursor.column_names)
                for row in cursor.fetchall():
                    values = ", ".join(sql_literal(item) for item in row)
                    handle.write(f"INSERT INTO `{name}` ({columns}) VALUES ({values});\n")
            handle.write("SET FOREIGN_KEY_CHECKS=1;\n")
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    finally:
        cursor.close()
    return path


def automatic_backup():
    try:
        return write_backup()
    except (MySQLError, OSError):
        log_error("Automatic backup failed")
        return None


def has_any_data():
    row = fetch_one(
        "SELECT (SELECT COUNT(*) FROM companies) + (SELECT COUNT(*) FROM works) AS total"
    )
    return int(row["total"]) > 0


def list_backup_files():
    paths = glob.glob(os.path.join(APP_DIR, "*_backup_*.sql"))
    return sorted(paths, key=os.path.getmtime, reverse=True)


def describe_backup(path):
    size_kb = max(1, os.path.getsize(path) // 1024)
    modified = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d-%m-%Y %H:%M")
    return f"{os.path.basename(path)}  ({size_kb} KB, {modified})"


def read_backup_file(path):
    if not os.path.isfile(path):
        raise ValueError("That file does not exist.")
    statements = []
    created = set()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            if handle.readline().strip() != BACKUP_MARKER:
                raise ValueError("This is not a backup file created by this application.")
            for number, line in enumerate(handle, start=2):
                line = line.rstrip("\r\n")
                if not line.strip() or line.startswith("--"):
                    continue
                match = BACKUP_STATEMENT_PATTERN.match(line)
                table = match and (match.group(2) or match.group(3) or match.group(4))
                if not match or not line.endswith(";") or (table and table not in TABLE_NAMES):
                    raise ValueError(
                        f"Unexpected content on line {number}. "
                        "The backup file may be damaged or edited."
                    )
                if match.group(3):
                    created.add(match.group(3))
                statements.append(line)
    except UnicodeDecodeError:
        raise ValueError("The file could not be read as a backup text file.")
    if created != set(TABLE_NAMES):
        raise ValueError("The backup file is incomplete: some tables are missing.")
    return statements


def apply_backup_statements(statements):
    cursor = get_connection().cursor()
    try:
        for statement in statements:
            cursor.execute(statement)
    finally:
        try:
            cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        except MySQLError:
            pass
        cursor.close()
    STATE["dirty"] = True


@safe_action
def backup_now():
    path = write_backup()
    show_result("Create Backup", f"Backup created:\n{path}")


@safe_action
def restore_from_backup():
    files = list_backup_files()
    options = [describe_backup(path) for path in files] + ["Enter a backup file path manually"]
    subtitle = f"Backups found in {APP_DIR}:" if files else "No backup files found in the application folder."
    choice = menu("Restore From Backup", options, subtitle=subtitle)
    if choice is None:
        return
    if choice < len(files):
        path = files[choice]
    else:
        print_header("Restore From Backup")
        raw = read_line("Full path of the backup file (Esc to cancel)")
        if raw is None:
            return
        path = raw.strip().strip('"')
    try:
        statements = read_backup_file(path)
    except ValueError as error:
        show_error(str(error))
        return
    if not confirm(
        "Restore this backup?",
        f"File: {os.path.basename(path)}\n\n"
        "All current companies and works will be REPLACED by the backup contents.\n"
        "A safety backup of the current data is created first.",
        "Yes, restore the backup",
    ):
        show_result("Restore From Backup", "Cancelled. Nothing was changed.")
        return
    safety_path = write_backup("_before_restore")
    try:
        apply_backup_statements(statements)
    except MySQLError as error:
        log_error("Restore failed")
        message = f"The restore failed: {describe_db_error(error)}\n"
        try:
            apply_backup_statements(read_backup_file(safety_path))
            message += "Your previous data was put back from the safety backup."
        except (MySQLError, ValueError):
            log_error("Recovery from safety backup failed")
            message += f"Automatic recovery also failed. Restore manually from:\n{safety_path}"
        show_error(message)
        return
    show_result(
        "Restore From Backup",
        f"Backup restored.\nA safety copy of the previous data is saved as:\n{safety_path}",
    )


def work_menu(company):
    options = [
        "Add Work",
        "Update Work",
        "Search Work",
        "Display Works",
        "Delete Work",
        "Return to Company Menu",
    ]
    subtitle = f"Company: {company['company_name']} (ID {company['company_id']})"
    index = 0
    while True:
        choice = menu("Work Management", options, subtitle=subtitle, start=index)
        if choice is None:
            return "back"
        if choice == 5:
            return "company"
        index = choice
        if choice == 0:
            add_work(company)
        elif choice == 1:
            update_work(company)
        elif choice == 2:
            search_work(company)
        elif choice == 3:
            display_works(company)
        elif choice == 4:
            delete_work(company)


def company_menu():
    options = [
        "Add Company",
        "Update Company",
        "Search Company",
        "Display All Companies",
        "Delete Company (Archive)",
        "Retrieve Archived Company",
        "Back to Main Menu",
    ]
    index = 0
    while True:
        choice = menu("Company Management", options, start=index)
        if choice is None or choice == 6:
            return
        index = choice
        if choice == 0:
            add_company()
        elif choice == 1:
            update_company()
        elif choice == 2:
            company = search_company()
            if company:
                work_menu(company)
        elif choice == 3:
            display_companies()
        elif choice == 4:
            archive_company()
        elif choice == 5:
            restore_company()


@safe_action
def open_work_management():
    company = select_company("Work Management - Select Company")
    if company is None:
        return
    if work_menu(company) == "company":
        company_menu()


def backup_menu():
    options = ["Create Backup Now", "Restore From Backup", "Back to Main Menu"]
    index = 0
    while True:
        choice = menu("Backup and Recovery", options, start=index)
        if choice is None or choice == 2:
            return
        index = choice
        if choice == 0:
            backup_now()
        else:
            restore_from_backup()


def run_main_menu():
    options = [
        "Company Management",
        "Work Management",
        "Backup and Recovery",
        "Exit Application",
    ]
    index = 0
    while True:
        choice = menu(
            "Main Menu",
            options,
            start=index,
            footer="Up/Down: move    Enter: select    Esc: exit",
        )
        if choice is None:
            if confirm("Exit the application?", yes_label="Yes, exit"):
                return
            continue
        index = choice
        if choice == 0:
            company_menu()
        elif choice == 1:
            open_work_management()
        elif choice == 2:
            backup_menu()
        else:
            return


def start_application():
    if msvcrt is None:
        print("This application uses Windows keyboard handling and must be run on Windows.")
        return False
    os.system("")
    values, existed = load_config()
    if not existed or validate_config(values):
        values = prompt_config(values)
        if values is None:
            return False
    while True:
        try:
            messages = initialize_database(values)
            STATE["conn"] = connect_to_mysql(values, True)
            break
        except MySQLError as error:
            log_error("Connection or initialisation failed")
            choice = menu(
                "Database Connection Problem",
                ["Retry", "Edit database settings", "Exit application"],
                subtitle=describe_db_error(error),
                footer="Up/Down: move    Enter: select    Esc: exit",
            )
            if choice is None or choice == 2:
                return False
            if choice == 1:
                edited = prompt_config(values)
                if edited is None:
                    return False
                values = edited
    STATE["config"] = values
    try:
        if has_any_data():
            path = automatic_backup()
            if path:
                messages.append(f"Startup backup created: {os.path.basename(path)}")
            else:
                messages.append("Warning: the startup backup could not be created.")
    except MySQLError:
        log_error("Startup data check failed")
    print_header("Starting")
    for message in messages:
        print(message)
    pause()
    return True


def shutdown_application():
    if STATE["conn"] is None:
        return
    try:
        if STATE["dirty"]:
            path = automatic_backup()
            if path:
                print(f"Backup created: {os.path.basename(path)}")
        STATE["conn"].close()
    except MySQLError:
        log_error("Shutdown failed")
    STATE["conn"] = None


def main():
    try:
        if start_application():
            run_main_menu()
    except KeyboardInterrupt:
        print("\nApplication interrupted.")
    finally:
        shutdown_application()
    print("Goodbye.")


if __name__ == "__main__":
    main()
