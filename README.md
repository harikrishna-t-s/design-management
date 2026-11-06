# Personal Design Management System

A lightweight, terminal-based application for a freelance designer to manage client companies and the design work done for them. Built with Python and MySQL as a single-file application, suitable for an academic project.

---

## Table of Contents

1. [Project Overview and Objectives](#1-project-overview-and-objectives)
2. [Features and Workflow](#2-features-and-workflow)
3. [Technology Stack](#3-technology-stack)
4. [System Architecture](#4-system-architecture)
5. [Installation on a Fresh Windows Laptop](#5-installation-on-a-fresh-windows-laptop)
6. [Database Initialization and Connection Configuration](#6-database-initialization-and-connection-configuration)
7. [Database Schema](#7-database-schema)
8. [Table Relationships](#8-table-relationships)
9. [Function Reference](#9-function-reference)
10. [Built-in Functions and Libraries Used](#10-built-in-functions-and-libraries-used)
11. [Running the Application](#11-running-the-application)
12. [Backup and Recovery](#12-backup-and-recovery)
13. [Validation Rules](#13-validation-rules)
14. [Common Errors and Troubleshooting](#14-common-errors-and-troubleshooting)
15. [Files in the Project Folder](#15-files-in-the-project-folder)

---

## 1. Project Overview and Objectives

The application is used by one person, the founder of a freelance design business. It stores:

- **Companies** (clients): name, owner, domain(s), contact person and the final approval person with contact details.
- **Works** (design jobs): type, colour theme, deadline, estimated time, description and status. Every work belongs to exactly one company.

Objectives:

- Keep the code simple, readable and in one file (`main.py`).
- Never lose data: deleting a company archives it and can be undone; backups are automatic.
- Be fully keyboard driven with arrow-key menus on Windows.
- Validate all input and show readable messages instead of Python errors.

---

## 2. Features and Workflow

### Main menu

| Option | What it does |
|---|---|
| Company Management | Add, update, search, list, archive and restore companies |
| Work Management | Pick a company, then manage its work records |
| Backup and Recovery | Create a backup now or restore from a backup file |
| Exit Application | Close the program (a backup is taken if data changed) |

The specification lists three main-menu entries. A fourth entry, *Backup and Recovery*, was added because the manual backup and restore features need a place in the menu.

### Navigation

| Key | Action |
|---|---|
| Up / Down | Move the highlight (wraps around at the ends) |
| Home / End | Jump to the first / last item |
| Page Up / Page Down | Jump a page in long lists |
| Enter | Select the highlighted item |
| Esc | Go back, or cancel the current form |
| Backspace | Delete a typed character in a prompt |

Unknown keys are ignored. Long lists scroll automatically.

### Company Management

1. **Add Company** – asks for company name, owner, one or more domains, contact person, final approval person name, and the approval person's phone and/or email. The company ID is generated automatically. A summary is shown for confirmation before saving.
2. **Update Company** – search and select a company, then change any field. Press Enter to keep a value; type `-` to clear an optional phone or email.
3. **Search Company** – search by company name, domain or owner name (partial matches work). Selecting a company opens its Work Management menu.
4. **Display All Companies** – table of company name, owner, domain(s) and final approval person.
5. **Delete Company (Archive)** – after confirmation the company and all its works are archived, not deleted.
6. **Retrieve Archived Company** – search archived companies by name and restore one together with all its works.

### Work Management

Every work is linked to a company ID. When you enter Work Management from the main menu you first choose a company.

1. **Add Work** – choose a work type from a menu (or type your own), choose a status, then enter colour theme, deadline, estimated hours and description. The work ID is generated automatically.
2. **Update Work** – search the company's works (by work ID, type or description), pick one, change any detail or the status.
3. **Search Work** – filter by work type, an exact deadline, a date range, due today, due in the next 7 days, deadline this month, overdue, or status. The search can cover the selected company or all active companies.
4. **Display Works** – all works of the selected company, or the works of all active companies. A summary line shows totals per status, and a *Due* column shows days left or overdue.
5. **Delete Work** – enter a work ID, review the details and confirm. Deletion is permanent.
6. **Return to Company Menu** – go back to Company Management. (Esc returns to the previous menu.)

### Archiving behaviour

- *Delete Company* sets the company's `is_archived` flag and flags all its works too. Nothing is removed from the database.
- Archived companies and their works disappear from lists and searches.
- *Retrieve Archived Company* clears the flags on the company and on all its works in one transaction.
- Each archive and restore action is recorded in the `archive_log` table.
- A company name stays reserved while the company is archived, so a duplicate cannot be created by accident. Restore the archived company instead.

---

## 3. Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.9 or newer (tested with 3.12) |
| Database | MySQL 8.x (also works with MariaDB 10.5+) |
| Database driver | `mysql-connector-python` (the only external dependency) |
| Interface | Terminal (Windows Terminal, PowerShell or Command Prompt) |
| Keyboard input | `msvcrt` (part of Python on Windows) |
| Target OS | Windows 10 or 11 |

---

## 4. System Architecture

The application is one Python file organised in layers. Each layer only calls the layers below it.

```
+------------------------------------------------------+
|  Menus          main menu, company menu, work menu,   |
|                 backup menu                           |
+------------------------------------------------------+
|  Actions        add_company, update_work, search_work, |
|                 archive_company, restore_from_backup...|
|                 (each wrapped by @safe_action)         |
+------------------------------------------------------+
|  Validation     check_* functions, collect_fields      |
+------------------------------------------------------+
|  Terminal UI    menu, read_line, confirm, print_table  |
+------------------------------------------------------+
|  Database layer fetch_all, fetch_one, execute,         |
|                 transaction, initialize_database       |
+------------------------------------------------------+
|  Backup layer   write_backup, read_backup_file,        |
|                 apply_backup_statements                |
+------------------------------------------------------+
        |                                  |
   MySQL server                   .sql backup files
```

Key design points:

- **One shared connection** is kept in the `STATE` dictionary. `get_connection()` checks it before each use and reconnects if it dropped.
- **Autocommit is on.** Multi-step changes (adding a company with domains, archiving, restoring) use `transaction()`, which commits on success and rolls back on any error.
- **Parameterized SQL everywhere.** User text is never pasted into SQL. The only values placed in SQL text are fixed table names and the configured database name, which is checked against a strict pattern.
- **Central error handling.** The `@safe_action` decorator catches database, file and unexpected errors, shows a friendly message and writes technical details to `error_log.txt`.
- **No classes.** State is a plain dictionary and behaviour is plain functions.

---

## 5. Installation on a Fresh Windows Laptop

### Step 1 – Install Python

1. Open <https://www.python.org/downloads/windows/> and download the latest Python 3 installer (64-bit).
2. Run the installer. **Tick "Add python.exe to PATH"** on the first screen, then click *Install Now*.
3. Open a new **Command Prompt** or **PowerShell** window and check:

   ```
   python --version
   pip --version
   ```

   Both commands should print a version number.

### Step 2 – Install MySQL Server

1. Open <https://dev.mysql.com/downloads/installer/> and download **MySQL Installer for Windows** (the larger "full" installer is fine; the web installer also works).
2. Run it and choose **Custom** (or *Server only*). Select **MySQL Server 8.x** and optionally **MySQL Workbench** (a graphical tool for viewing the data).
3. Continue through the wizard with the default settings:
   - *Type and Networking*: Config Type **Development Computer**, port **3306**.
   - *Authentication Method*: **Use Strong Password Encryption** (the default).
   - *Accounts and Roles*: set a **root password** and remember it.
   - *Windows Service*: keep **Configure MySQL Server as a Windows Service** ticked and **Start the MySQL Server at System Startup** ticked.
4. Finish the wizard. The MySQL service now runs in the background.

To verify, open **Services** (press `Win + R`, type `services.msc`) and check that **MySQL80** has the status *Running*.

You do **not** need to create the database or tables by hand. The application creates them.

### Step 3 – Put the project in a folder

Create a folder, for example `C:\DesignManager`, and copy `main.py` into it (and optionally `main_documented.py` and `README.md`).

### Step 4 – Install the Python dependency

Open a Command Prompt in that folder and run:

```
cd C:\DesignManager
python -m pip install mysql-connector-python
```

This is the only external package needed. Everything else comes with Python.

### Step 5 – Run the program

```
python main.py
```

On the first run you are asked for the MySQL connection settings (see the next section).

---

## 6. Database Initialization and Connection Configuration

### Connection settings

Credentials are **not** written in the code. They are stored in `db_config.ini`, in the same folder as `main.py`.

On the first run the application asks for each value and creates the file:

| Setting | Default | Meaning |
|---|---|---|
| host | `localhost` | Where MySQL runs |
| port | `3306` | MySQL port |
| user | `root` | MySQL user |
| password | *(empty)* | Password typed with `*` masking |
| database | `design_management` | Database name (letters, digits, underscore) |

Example `db_config.ini`:

```ini
[mysql]
host = localhost
port = 3306
user = root
password = your_password_here
database = design_management
```

You can edit this file in Notepad at any time. If the connection fails at start-up, the menu offers **Retry**, **Edit database settings** and **Exit application**.

Security note: the password is stored as plain text in `db_config.ini`. This is acceptable for a personal laptop. Do not share or publish that file.

### Automatic initialization

At every start the application:

1. Connects to the MySQL server.
2. Creates the database **only if it does not exist**.
3. Lists the existing tables and creates **only the missing ones** (`CREATE TABLE IF NOT EXISTS`).
4. Leaves existing tables and rows untouched. Initialization never drops, truncates or overwrites data.
5. Creates a start-up backup if the database contains data.

The start-up screen reports what happened, for example *"Using existing database"* and *"All required tables are present."*

---

## 7. Database Schema

Database name (default): `design_management`. Engine: InnoDB. Character set: `utf8mb4`.

### Tables at a glance

| Table | Purpose | Primary key |
|---|---|---|
| `companies` | Client companies, with the archive flag | `company_id` (auto-increment) |
| `company_domains` | One row per domain of a company | `domain_id` (auto-increment) |
| `works` | Design work records | `work_id` (auto-increment) |
| `archive_log` | History of archive and restore actions | `log_id` (auto-increment) |

### Column details

**`companies`**

| Column | Type | Notes |
|---|---|---|
| company_id | INT UNSIGNED | Auto-generated unique ID |
| company_name | VARCHAR(150) | Required, **unique** |
| owner_name | VARCHAR(100) | Required, indexed |
| contact_person | VARCHAR(100) | Required |
| approver_name | VARCHAR(100) | Final approval person, required |
| approver_phone | VARCHAR(20) | Optional if email is given |
| approver_email | VARCHAR(120) | Optional if phone is given |
| is_archived | TINYINT(1) | 0 = active, 1 = archived, indexed |
| archived_at | DATETIME | Set when archived |
| created_at / updated_at | DATETIME | Maintained automatically |

**`company_domains`**

| Column | Type | Notes |
|---|---|---|
| domain_id | INT UNSIGNED | Auto-generated |
| company_id | INT UNSIGNED | Foreign key to `companies` |
| domain | VARCHAR(150) | Required, **unique** across all companies |

**`works`**

| Column | Type | Notes |
|---|---|---|
| work_id | INT UNSIGNED | Auto-generated unique ID |
| company_id | INT UNSIGNED | Foreign key to `companies` |
| work_type | VARCHAR(60) | Logo, Banner, Poster, ... indexed |
| colour_theme | VARCHAR(100) | Required |
| deadline | DATE | Required, indexed |
| estimated_hours | DECIMAL(6,2) | Must be above 0 |
| description | TEXT | Required |
| status | ENUM | `Pending`, `In Progress`, `Completed`; indexed |
| is_archived | TINYINT(1) | Follows the company's archive state |
| created_at / updated_at | DATETIME | Maintained automatically |

**`archive_log`**

| Column | Type | Notes |
|---|---|---|
| log_id | INT UNSIGNED | Auto-generated |
| company_id | INT UNSIGNED | Foreign key to `companies` |
| action | ENUM | `ARCHIVED` or `RESTORED` |
| works_affected | INT UNSIGNED | Number of works archived or restored |
| action_time | DATETIME | When it happened |

### Exact SQL used to create the tables

```sql
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```sql
CREATE TABLE IF NOT EXISTS `company_domains` (
    `domain_id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `company_id` INT UNSIGNED NOT NULL,
    `domain` VARCHAR(150) NOT NULL,
    PRIMARY KEY (`domain_id`),
    UNIQUE KEY `uq_domain` (`domain`),
    CONSTRAINT `fk_domain_company` FOREIGN KEY (`company_id`)
        REFERENCES `companies` (`company_id`)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```sql
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```sql
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

Notes:

- `CHECK` constraints are enforced by MySQL 8.0.16 and newer. On older servers they are ignored, but the application validates the same rules.
- All searches use parameterized `LIKE` queries; the percent and underscore characters you type are treated literally.

---

## 8. Table Relationships

```
companies (1) ----< (many) company_domains
    |
    +---------------< (many) works
    |
    +---------------< (many) archive_log
```

| Relationship | Foreign key | On delete | Why |
|---|---|---|---|
| `company_domains.company_id` to `companies.company_id` | `fk_domain_company` | CASCADE | Domains have no meaning without their company |
| `works.company_id` to `companies.company_id` | `fk_work_company` | **RESTRICT** | A company with works can never be hard-deleted, so work records are always preserved |
| `archive_log.company_id` to `companies.company_id` | `fk_log_company` | RESTRICT | Keeps the history intact |

Archiving is a **soft delete**. The `is_archived` flag on `companies` and on `works` decides what the application shows. Restoring flips the flags back for the company and all of its works inside one transaction, so either everything is restored or nothing is.

---

## 9. Function Reference

Functions are listed in the order they appear in the file, grouped by role. The one-line descriptions come from the docstrings in `main_documented.py`.

### General helpers

| Function | Purpose |
|---|---|
| `to_text()` | Return value as str, decoding bytes that some MySQL versions return. |
| `log_error()` | Append the current exception and its traceback to error_log.txt. |
| `describe_db_error()` | Translate a MySQL error into a short, readable message. |
| `safe_action()` | Decorator that turns any error in a menu action into a friendly message. |
| `truncate()` | Shorten text to width characters, ending with '...' when cut. |
| `like_pattern()` | Build a safe LIKE pattern that matches text anywhere in a value. |
| `format_date()` | Format a date as DD-MM-YYYY. |
| `format_hours()` | Format a Decimal hour value without trailing zeros. |
| `due_text()` | Return a short 'days left' text for a work record. |

### Terminal output

| Function | Purpose |
|---|---|
| `terminal_width()` | Return the usable terminal width. |
| `terminal_height()` | Return the terminal height in lines. |
| `clear_screen()` | Clear the terminal using ANSI escape codes. |
| `print_header()` | Clear the screen and print the application banner with a page title. |
| `print_table()` | Print rows as an aligned text table that fits the terminal width. |
| `show_result()` | Show a full-screen message and wait for a key press. |
| `show_error()` | Show an error message and wait for a key press. |

### Keyboard input and menus

| Function | Purpose |
|---|---|
| `get_key()` | Read one key press and return a name such as 'UP', 'ENTER' or 'a'. |
| `pause()` | Wait for any key press. |
| `read_line()` | Read a line of text key by key. |
| `menu()` | Show an arrow-key menu and return the chosen index, or None for Esc. |
| `confirm()` | Ask a yes/no question with arrow keys. 'No' is highlighted first. |

### Validation

| Function | Purpose |
|---|---|
| `check_text()` | Validate free text. Returns (clean_value, error_message). |
| `check_person_name()` | Validate a person's name (letters, spaces, dots, apostrophes, hyphens). |
| `check_company_name()` | Validate a company name and reject duplicates, including archived ones. |
| `normalise_domain()` | Clean a domain: lower case, no scheme, no 'www.', no path. |
| `check_domains()` | Validate a comma-separated domain list. Returns (list_of_domains, error). |
| `check_phone()` | Validate an optional phone number. Returns (clean_value, error). |
| `check_email()` | Validate the approver email. A phone or an email must be present. |
| `parse_date()` | Parse DD-MM-YYYY (also accepts / and . separators). Returns a date or None. |
| `check_date()` | Validate a plain date field. Returns (date, error). |
| `check_deadline()` | Validate a work deadline. |
| `check_hours()` | Validate the estimated completion time in hours. Returns (Decimal, error). |
| `check_id()` | Validate a numeric ID. Returns (int_id, error). |
| `collect_fields()` | Prompt for each field in turn and validate it. |

### Database layer

| Function | Purpose |
|---|---|
| `load_config()` | Read db_config.ini. Returns (settings_dict, file_existed). |
| `save_config()` | Write the connection settings to db_config.ini. |
| `validate_config()` | Return an error message if the settings are unusable, else None. |
| `prompt_config()` | Ask the user for connection settings and save them. Returns settings or None. |
| `connect_to_mysql()` | Open a MySQL connection. Uses autocommit; transactions are explicit. |
| `initialize_database()` | Create the database and any missing tables. Never touches existing data. |
| `get_connection()` | Return the live connection, reconnecting if it dropped. |
| `fetch_all()` | Run a SELECT and return all rows as dictionaries. |
| `fetch_one()` | Run a SELECT and return the first row as a dictionary, or None. |
| `transaction()` | Run work(cursor) inside one transaction. |
| `execute()` | Run one INSERT/UPDATE/DELETE in a transaction. Returns the new row ID. |

### Company helpers

| Function | Purpose |
|---|---|
| `find_companies()` | Find companies. Active search matches name, owner or domain. |
| `company_label()` | Return a one-line description of a company for menus. |
| `format_company_details()` | Return a multi-line text block describing a company. |
| `select_company()` | Search for a company and let the user pick one. Returns a row or None. |
| `company_fields()` | Return the prompt definitions used by Add Company and Update Company. |

### Company actions

| Function | Purpose |
|---|---|
| `add_company()` | Collect details for a new company and save it with its domains. |
| `update_company()` | Select a company and edit its stored information. |
| `search_company()` | Search for a company. Returns the selected company row, or None. |
| `display_companies()` | Show every active company in a table. |
| `archive_company()` | Archive a company and its works. Nothing is permanently deleted. |
| `restore_company()` | Restore an archived company together with its work records. |

### Work helpers

| Function | Purpose |
|---|---|
| `query_works()` | Return active works joined with their company name. |
| `get_work()` | Return one active work of a company, or None. |
| `work_label()` | Return a one-line description of a work for menus. |
| `format_work_details()` | Return a multi-line text block describing a work record. |
| `show_work_table()` | Print works as a table with a status summary line. |
| `select_work()` | Search a company's works and let the user pick one. Returns a row or None. |
| `choose_work_type()` | Pick a work type from a menu or type a custom one. Returns text or None. |
| `choose_status()` | Pick a work status from a menu. Returns a valid status or None. |
| `work_fields()` | Return the text prompts shared by Add Work and Update Work. |
| `build_work_filter()` | Ask for the input a search filter needs. |

### Work actions

| Function | Purpose |
|---|---|
| `add_work()` | Collect details for a new work record and save it for the company. |
| `update_work()` | Select a work record and edit its details and status. |
| `search_work()` | Search works by type, deadline, date range or status. |
| `display_works()` | Show works for the selected company or for all active companies. |
| `delete_work()` | Delete one work record of the company by its work ID, after confirmation. |

### Backup and recovery

| Function | Purpose |
|---|---|
| `sql_literal()` | Convert a Python value into an SQL literal for the backup file. |
| `write_backup()` | Write a timestamped SQL backup next to the application. Returns its path. |
| `automatic_backup()` | Create a backup without ever failing the caller. Returns the path or None. |
| `has_any_data()` | Return True if the database holds at least one company or work. |
| `list_backup_files()` | Return backup files in the application folder, newest first. |
| `describe_backup()` | Return a menu label for a backup file. |
| `read_backup_file()` | Read and check a backup file. Returns its SQL statements. |
| `apply_backup_statements()` | Run backup statements. Foreign key checks are always switched back on. |
| `backup_now()` | Create a manual backup. |
| `restore_from_backup()` | Replace the current data with the contents of a backup file. |

### Menus

| Function | Purpose |
|---|---|
| `work_menu()` | Work Management menu for one company. |
| `company_menu()` | Company Management menu. |
| `open_work_management()` | Main-menu entry to Work Management: pick a company first. |
| `backup_menu()` | Backup and Recovery menu. |
| `run_main_menu()` | Main menu loop. Returns when the user confirms exit. |

### Startup and shutdown

| Function | Purpose |
|---|---|
| `start_application()` | Load settings, connect, initialise the database and take a startup backup. |
| `shutdown_application()` | Take an exit backup if data changed, then close the connection. |
| `main()` | Program entry point. |


### Nested functions

- `wrapper` (inside `safe_action`) – runs the decorated action and converts errors to messages.
- `work` (inside `add_company`, `update_company`, `archive_company`, `restore_company`) – the group of SQL statements passed to `transaction()`.
- `validator` lambdas (in `company_fields` and `work_fields`) – small adapters that connect each prompt to its `check_*` function.

---

## 10. Built-in Functions and Libraries Used

### Python built-in functions

| Function | Used for |
|---|---|
| `print()` | Writing text to the terminal |
| `len()` | Lengths of text, lists and option sets |
| `str()`, `int()`, `repr()` | Converting values |
| `range()` | Looping over visible menu rows |
| `enumerate()` | Line numbers when reading backup files |
| `sorted()` | Sorting domains and backup files |
| `sum()`, `max()`, `min()` | Column width calculation and menu paging |
| `any()`, `all()` | Checking changes and allowed characters |
| `dict()`, `list()`, `set()` | Copying and comparing collections |
| `isinstance()` | Choosing how to write a value into a backup |
| `open()` | Reading and writing config, backup and log files |
| `zip()`, `reversed()` | Table printing and table drop order |

### String methods

`strip()`, `split()`, `join()`, `lower()`, `replace()`, `ljust()`, `startswith()`, `endswith()`, `isalpha()`, `isdigit()`, `isascii()`, `isprintable()`, `count()`, and `bytes.hex()`.

### Standard library modules

| Module | Purpose |
|---|---|
| `os` | File paths, `os.path.join`, `os.remove`, `os.path.getmtime` |
| `sys` | Writing to standard output without a newline |
| `re` | Pattern checks for domains, emails, phone numbers, backup lines |
| `datetime` | `date`, `datetime`, `timedelta` for deadlines and timestamps |
| `calendar` | `monthrange` to find the last day of the month |
| `decimal` | Exact `Decimal` values for estimated hours |
| `configparser` | Reading and writing `db_config.ini` |
| `glob` | Finding backup files |
| `shutil` | `get_terminal_size` for table and menu layout |
| `functools` | `wraps` for the `safe_action` decorator |
| `traceback` | Writing error details to `error_log.txt` |
| `msvcrt` | `getwch()` to read single key presses on Windows |

### Third-party library

| Package | Purpose |
|---|---|
| `mysql-connector-python` | `mysql.connector.connect`, cursors, `Error` exceptions |

---

## 11. Running the Application

Open Command Prompt or PowerShell, go to the project folder and run:

```
cd C:\DesignManager
python main.py
```

Recommended: use **Windows Terminal** (installed by default on Windows 11, free in the Microsoft Store for Windows 10). The menu highlight uses ANSI colours, which Windows Terminal and current PowerShell / Command Prompt windows support. Maximise the window or make it wide enough to read the tables.

Typical session:

1. Start the program and read the start-up status, then press any key.
2. Choose **Company Management**, then **Add Company** and fill the prompts.
3. Choose **Search Company**, select the company and add work from its Work Management menu.
4. Choose **Exit Application** when done. A backup is created if you changed data.

Date format everywhere: **DD-MM-YYYY** (for example `25-12-2026`). The separators `/` and `.` are also accepted when typing.

Estimated completion time is entered in **hours** (for example `6` or `7.5`).

---

## 12. Backup and Recovery

### Automatic backups

| When | Condition |
|---|---|
| At start-up | If the database already contains data |
| At exit | If anything was changed during the session |

### Manual backup

Main Menu, then **Backup and Recovery**, then **Create Backup Now**.

### Backup files

- Saved **in the same folder as `main.py`**.
- Named `<database>_backup_<YYYYMMDD>_<HHMMSS>.sql`, for example `design_management_backup_20261106_143005.sql`.
- Files are created in exclusive mode, so an existing backup is **never overwritten**. If two backups happen in the same second, a `_1`, `_2` suffix is added.
- Plain-text SQL: table drops, table creation and one `INSERT` per row.
- The backup is produced by the application itself, so the `mysqldump` tool is not needed.

### Restoring from a backup

1. Main Menu, then **Backup and Recovery**, then **Restore From Backup**.
2. Pick a file from the list (newest first), or choose *Enter a backup file path manually*.
3. The file is checked first. It must be a complete backup made by this application; anything else is rejected without touching the database.
4. Confirm. The default highlighted choice is *No*.
5. A **safety backup** of the current data is saved first as `<database>_backup_<time>_before_restore.sql`.
6. The backup replaces the current companies, works and history.

If the restore fails part-way, the application tries to put the previous data back from the safety backup and tells you the result. If that also fails, the message shows the safety backup path so you can restore it manually.

### Restoring without the application (optional)

Backups made by this application are ordinary SQL and can be loaded with the MySQL client:

```
mysql -u root -p design_management < design_management_backup_20261106_143005.sql
```

### Recommended habit

Copy the `.sql` files to a USB drive or cloud folder now and then. Backups in the project folder protect against mistakes, not against a lost laptop.

---

## 13. Validation Rules

| Field | Rule |
|---|---|
| All required fields | Cannot be empty; extra spaces are trimmed |
| Company name | Max 150 characters; must be unique (case-insensitive), including archived companies |
| Person names | Letters, spaces, dots, apostrophes, hyphens; must start with a letter |
| Domains | Valid format such as `example.com`; `https://`, `www.` and paths are removed; each domain can belong to only one company |
| Phone | 7 to 15 digits, optional leading `+`; spaces, dashes and brackets allowed |
| Email | Basic `name@domain.tld` format |
| Approval contact | At least one of phone or email is required |
| Dates | `DD-MM-YYYY`, real calendar dates, years 2000 to 2100 |
| Deadline | Cannot be in the past, except for *Completed* works or when updating a work without changing its deadline |
| Estimated hours | Number above 0, at most 9999.99 |
| Work status | Only `Pending`, `In Progress` or `Completed` (chosen from a menu) |
| Company / work IDs | Positive whole numbers that must exist (and, for works, belong to the selected company) |
| Database settings | Port 1 to 65535; database name letters, digits and underscore only |

---

## 14. Common Errors and Troubleshooting

| Message or symptom | Cause | Fix |
|---|---|---|
| `'python' is not recognized` | Python is not on PATH | Reinstall Python and tick *Add python.exe to PATH*, then open a new terminal |
| `No module named 'mysql'` | Driver not installed | Run `python -m pip install mysql-connector-python` |
| "Cannot connect to the MySQL server" | MySQL service is stopped, or wrong host/port | Open `services.msc`, start **MySQL80**; check host and port in `db_config.ini` |
| "Access denied. Check the MySQL user name and password" | Wrong credentials | Choose *Edit database settings*, or fix `db_config.ini` |
| "The MySQL user does not have permission..." | User cannot create or use the database | Use `root`, or ask an administrator to grant privileges |
| "The connection to the MySQL server was lost" | Server restarted or idle timeout | Repeat the action; the connection is re-opened automatically |
| "This application uses Windows keyboard handling..." | Program run on Linux or macOS | Run it on Windows |
| Menu shows strange characters like `[7m` | Old console without ANSI colour support | Use Windows Terminal, or update Windows 10 |
| Arrow keys print letters instead of moving | Program started in an unsupported terminal (for example inside some editors' output panes) | Run it from Command Prompt, PowerShell or Windows Terminal |
| Table lines wrap and look messy | Window too narrow | Widen or maximise the window |
| "A company with this name is in the archive" | The name belongs to an archived company | Use *Retrieve Archived Company* |
| "The domain ... already belongs to ..." | Domains must be unique | Remove the domain from the other company first |
| "The deadline cannot be in the past" | Entered a past date for an open work | Enter today or a later date, or set the status to *Completed* |
| "This is not a backup file created by this application" | Wrong file chosen | Choose a `_backup_` file made by this program |
| "Unexpected content on line N" | Backup file was edited or damaged | Use another backup |
| "Something unexpected went wrong" | Unforeseen error; the action was cancelled | Read `error_log.txt` in the project folder for technical details |

### Where problems are recorded

Technical details of every unexpected error go to `error_log.txt` (same folder as `main.py`). The terminal only shows a short, readable message.

### Starting over with an empty database

Stop the program, then in MySQL run `DROP DATABASE design_management;` (this deletes all data; make a backup first). The next start creates a fresh database.

---

## 15. Files in the Project Folder

| File | Description |
|---|---|
| `main.py` | The complete application, without comments |
| `main_documented.py` | Identical code with explanatory comments and docstrings |
| `README.md` | This document |
| `db_config.ini` | Created on first run; MySQL connection settings |
| `*_backup_*.sql` | Backup files created by the application |
| `error_log.txt` | Created only if an unexpected error occurs |
