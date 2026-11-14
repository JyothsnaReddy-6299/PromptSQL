import unittest
from app.services.table_translator import translate_modification_tables

class TestTableColumnCollisionModification(unittest.TestCase):
    """
    Tests ensuring that when a table's friendly name matches one of its column names
    (e.g. table 'marks' containing column 'marks'), table translation converts ONLY
    the table reference into the authorized physical name and leaves column names intact.
    """

    def test_insert_column_name_matches_table_name(self):
        sql = "INSERT INTO `marks` (`roll_no`, `name`, `subject`, `marks`) VALUES ('ch.sc.u4cse25219', 'jyothsna', 'english', '98')"
        translated = translate_modification_tables(
            sql=sql,
            friendly_name="marks",
            physical_table_name="marks_usr_8",
            authorized_tables=["marks_usr_8"]
        )
        # Table must be translated to `marks_usr_8`
        self.assertIn("`marks_usr_8`", translated)
        # Column name `marks` must NOT be translated to `marks_usr_8`
        self.assertIn("`marks`", translated)
        self.assertNotIn("`marks_usr_8`) VALUES", translated)
        self.assertIn("`marks`) VALUES", translated)

    def test_insert_without_backticks(self):
        sql = "INSERT INTO marks (roll_no, name, subject, marks) VALUES ('123', 'alice', 'math', '100')"
        translated = translate_modification_tables(
            sql=sql,
            friendly_name="marks",
            physical_table_name="marks_usr_8",
            authorized_tables=["marks_usr_8"]
        )
        self.assertIn("`marks_usr_8`", translated)
        self.assertIn("marks", translated)
        self.assertNotIn("marks_usr_8) VALUES", translated)

    def test_update_column_name_matches_table_name(self):
        sql = "UPDATE `marks` SET `marks` = 100 WHERE `marks` < 50"
        translated = translate_modification_tables(
            sql=sql,
            friendly_name="marks",
            physical_table_name="marks_usr_8",
            authorized_tables=["marks_usr_8"]
        )
        self.assertTrue(translated.startswith("UPDATE `marks_usr_8`"))
        self.assertIn("SET `marks` = 100", translated)
        self.assertIn("WHERE `marks` < 50", translated)

    def test_delete_column_name_matches_table_name(self):
        sql = "DELETE FROM `marks` WHERE `marks` = 0"
        translated = translate_modification_tables(
            sql=sql,
            friendly_name="marks",
            physical_table_name="marks_usr_8",
            authorized_tables=["marks_usr_8"]
        )
        self.assertTrue(translated.startswith("DELETE FROM `marks_usr_8`"))
        self.assertIn("WHERE `marks` = 0", translated)

    def test_alter_table_preserves_new_column_names(self):
        sql = "ALTER TABLE `marks` ADD COLUMN `marks_percentage` DECIMAL(5,2)"
        translated = translate_modification_tables(
            sql=sql,
            friendly_name="marks",
            physical_table_name="marks_usr_8",
            authorized_tables=["marks_usr_8"]
        )
        self.assertIn("ALTER TABLE `marks_usr_8`", translated)
        self.assertIn("`marks_percentage`", translated)

if __name__ == "__main__":
    unittest.main()
