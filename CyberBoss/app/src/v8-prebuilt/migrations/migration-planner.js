'use strict';
const TABLES=['inbox','jobs','events','outbox','sessions','reminders'];
function quoteIdentifier(value){if(!/^[A-Za-z_][A-Za-z0-9_]*$/.test(value))throw new TypeError('unsafe identifier');return `"${value}"`;}
function planUserScopeMigration({schema}){
  const steps=[];
  for(const table of TABLES){
    const cols=new Set(schema[table]||[]);if(cols.size===0)continue;
    const q=quoteIdentifier(table);
    if(!cols.has('user_id'))steps.push({op:'add_column',table,column:'user_id',sql:`ALTER TABLE ${q} ADD COLUMN user_id TEXT`});
    steps.push({op:'backfill_owner',table,sql:`UPDATE ${q} SET user_id = :ownerUserId WHERE user_id IS NULL OR user_id = ''`});
    const guard=`NEW.user_id IS NULL OR NEW.user_id = '' OR NOT EXISTS (SELECT 1 FROM users WHERE user_id = NEW.user_id)`;
    steps.push({op:'guard_insert',table,sql:`CREATE TRIGGER IF NOT EXISTS ${quoteIdentifier(`trg_${table}_valid_user_insert`)} BEFORE INSERT ON ${q} WHEN ${guard} BEGIN SELECT RAISE(ABORT, 'valid user_id required'); END`});
    steps.push({op:'guard_update',table,sql:`CREATE TRIGGER IF NOT EXISTS ${quoteIdentifier(`trg_${table}_valid_user_update`)} BEFORE UPDATE OF user_id ON ${q} WHEN ${guard} BEGIN SELECT RAISE(ABORT, 'valid user_id required'); END`});
    steps.push({op:'index',table,sql:`CREATE INDEX IF NOT EXISTS ${quoteIdentifier(`idx_${table}_user`)} ON ${q}(user_id)`});
  }
  return steps;
}
module.exports={TABLES,quoteIdentifier,planUserScopeMigration};
