import tempfile,unittest,sqlite3
from pathlib import Path
from signal_lattice.backup import backup_sqlite,restore_sqlite
class T(unittest.TestCase):
 def test_backup_restore(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);db=p/'a.db';c=sqlite3.connect(db);c.execute('create table x(v)');c.execute('insert into x values (1)');c.commit();c.close();r=backup_sqlite(db,p/'b.db');db.unlink();restore_sqlite(p/'b.db',db,r['sha256']);c=sqlite3.connect(db);self.assertEqual(c.execute('select v from x').fetchone()[0],1);c.close()
