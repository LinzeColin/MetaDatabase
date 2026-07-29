'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { UserContext } = require('../../src/v8-prebuilt/users/user-context');
const { UserCompanionService } = require('../../src/v8-prebuilt/companion/user-companion-service');

function ctx(userId, role = 'user') { return new UserContext({ userId, role, status: 'active', principalHash: 'hash' }); }

test('timeline diary and reminder are always server-scoped to the active user', async () => {
  const rows=[];
  const repository={
    async append(row){ rows.push(row); return row; },
    async list({userId,kind,limit}){ return rows.filter((row)=>row.userId===userId&&row.kind===kind).slice(0,limit); },
  };
  const service=new UserCompanionService({repository});
  const a=ctx('usr_AAAAAAAAAAAAAAAAAAAA');
  const b=ctx('usr_BBBBBBBBBBBBBBBBBBBB');
  await service.append(a,{kind:'timeline',entryId:'event:0001',payload:{title:'A'}});
  await service.append(b,{kind:'timeline',entryId:'event:0001',payload:{title:'B'}});
  assert.equal((await service.list(a,{kind:'timeline'})).length,1);
  assert.equal((await service.list(a,{kind:'timeline'}))[0].payload.title,'A');
  assert.equal((await service.list(b,{kind:'timeline'}))[0].payload.title,'B');
});

test('ordinary user cannot invoke owner companion tools', async () => {
  const service=new UserCompanionService({repository:{append:async()=>{},list:async()=>[]},ownerToolHandlers:{shell:async()=>true}});
  await assert.rejects(()=>service.invokeOwnerTool(ctx('usr_AAAAAAAAAAAAAAAAAAAA'),{tool:'shell'}),/OWNER_ONLY/);
  assert.equal(await service.invokeOwnerTool(ctx('usr_OOOOOOOOOOOOOOOOOOOO','owner'),{tool:'shell'}),true);
  await assert.rejects(()=>service.invokeOwnerTool(ctx('usr_OOOOOOOOOOOOOOOOOOOO','owner'),{tool:'unknown'}),/OWNER_TOOL_NOT_ALLOWED/);
});
