
# SBM
# Create the MIsoTEx feedback database and table using the existing MySQL account.
# This script does not create users or change existing passwords.

import getpass
import mysql.connector
from mysql.connector import Error

DB_NAME = "misotex_feedback"
TABLE_NAME = "user_feedback"


def main():
    username = input("MySQL username [curator]: ").strip() or "curator"
    password = getpass.getpass("MySQL password: ")

    conn = None
    cursor = None

    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="curator@localhost",
            password="curator_password",
            connection_timeout=5
        )
        cursor = conn.cursor()

        # Create the separate feedback database.
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )

        # Create the feedback table.
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS `{DB_NAME}`.`{TABLE_NAME}` (
                feedback_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                rating TINYINT UNSIGNED NULL,
                ease_of_use VARCHAR(30) NULL,
                feedback_type VARCHAR(40) NOT NULL,
                module VARCHAR(100) NULL,
                comments TEXT NOT NULL,
                country VARCHAR(100) NULL,
                institution VARCHAR(255) NULL,
                contact_email VARCHAR(254) NULL,
                status ENUM(
                    'New',
                    'Under Review',
                    'Resolved',
                    'Closed'
                ) NOT NULL DEFAULT 'New',
                PRIMARY KEY (feedback_id),
                INDEX idx_submitted_at (submitted_at),
                INDEX idx_feedback_type (feedback_type),
                INDEX idx_status (status)
            ) ENGINE=InnoDB
        """)

        print("\nDatabase and table created or already exist.")

        cursor.execute(f"SHOW COLUMNS FROM `{DB_NAME}`.`{TABLE_NAME}`")
        print("\nTable columns:")
        for column in cursor.fetchall():
            print("-", column[0], column[1])

        print("\nSetup completed successfully.")

    except Error as err:
        print("\nMySQL error:", err.msg)
        print(
            "Check that this account has CREATE DATABASE and CREATE "
            "TABLE privileges."
        )

    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    main()

