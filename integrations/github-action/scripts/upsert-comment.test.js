'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const upsert = require('./upsert-comment.js');

const MARKER = upsert.MARKER;

function fakeGithub(existing) {
  const calls = { created: [], updated: [] };
  return {
    calls,
    paginate: async (_fn, params) => {
      calls.listParams = params;
      return existing;
    },
    rest: {
      issues: {
        listComments: () => {},
        createComment: async (p) => {
          calls.created.push(p);
          return { data: { id: 900 } };
        },
        updateComment: async (p) => {
          calls.updated.push(p);
          return { data: { id: p.comment_id } };
        },
      },
    },
  };
}

const context = {
  repo: { owner: 'acme', repo: 'agent' },
  payload: { pull_request: { number: 7 } },
  issue: { number: 7 },
};

test('creates a comment when none carries the marker', async () => {
  const github = fakeGithub([{ id: 1, body: 'looks good' }, { id: 2, body: 'x\n' + MARKER }]);
  const body = `${MARKER}\n## Gauntlet: PASS\n`;
  const res = await upsert({ github, context, body });
  assert.deepEqual(res, { action: 'created', id: 900 });
  assert.equal(github.calls.created.length, 1);
  assert.equal(github.calls.created[0].issue_number, 7);
  assert.equal(github.calls.created[0].owner, 'acme');
  assert.equal(github.calls.updated.length, 0);
});

test('updates the comment whose body starts with the marker', async () => {
  const github = fakeGithub([
    { id: 1, body: 'unrelated' },
    { id: 5, body: `${MARKER}\nold` },
  ]);
  const res = await upsert({ github, context, body: `${MARKER}\nnew` });
  assert.deepEqual(res, { action: 'updated', id: 5 });
  assert.equal(github.calls.updated[0].comment_id, 5);
  assert.equal(github.calls.updated[0].body, `${MARKER}\nnew`);
  assert.equal(github.calls.created.length, 0);
});

test('with duplicates the newest marker comment is the one updated', async () => {
  const github = fakeGithub([
    { id: 5, body: `${MARKER}\nold` },
    { id: 8, body: `${MARKER}\nnewer` },
  ]);
  const res = await upsert({ github, context, body: `${MARKER}\nx` });
  assert.equal(res.id, 8);
});

test('rejects a body without the marker', async () => {
  await assert.rejects(() => upsert({ github: fakeGithub([]), context, body: 'hello' }), /must start with/);
});

test('truncates bodies over the GitHub limit', async () => {
  const github = fakeGithub([]);
  await upsert({ github, context, body: MARKER + 'a'.repeat(70000) });
  assert.ok(github.calls.created[0].body.length <= 65000);
});

test('reads the body from a file', async () => {
  const fs = require('node:fs');
  const os = require('node:os');
  const path = require('node:path');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'upsert-'));
  const file = path.join(dir, 'c.md');
  fs.writeFileSync(file, `${MARKER}\nfrom file`);
  const github = fakeGithub([]);
  await upsert({ github, context, bodyFile: file });
  assert.match(github.calls.created[0].body, /from file/);
});
