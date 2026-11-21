'use strict';

// Creates or updates the single Gauntlet comment on a pull request. Run it through
// actions/github-script:
//
//   const upsert = require(`${process.env.GITHUB_ACTION_PATH}/scripts/upsert-comment.js`);
//   await upsert({ github, context, core, bodyFile: 'gate-comment.md' });
//
// The comment is recognised by its first line, the marker below, so a second run on the same
// pull request edits the comment instead of adding another.

const fs = require('node:fs');

const MARKER = '<!-- gauntlet-report -->';
const MAX_BODY = 65000; // GitHub rejects bodies over 65,536 characters

async function findExisting(github, params) {
  const comments = await github.paginate(github.rest.issues.listComments, {
    ...params,
    per_page: 100,
  });
  // Newest first, so a stray duplicate never shadows the live comment.
  return [...comments].reverse().find((c) => typeof c.body === 'string' && c.body.startsWith(MARKER));
}

async function upsertComment({ github, context, core, body, bodyFile }) {
  const text = body !== undefined ? body : fs.readFileSync(bodyFile, 'utf8');
  if (!text.startsWith(MARKER)) {
    throw new Error(`comment body must start with ${MARKER}`);
  }
  const issue_number = context.payload.pull_request
    ? context.payload.pull_request.number
    : context.issue.number;
  const params = { owner: context.repo.owner, repo: context.repo.repo, issue_number };
  const payload = text.length > MAX_BODY ? text.slice(0, MAX_BODY) : text;

  const existing = await findExisting(github, params);
  if (existing) {
    await github.rest.issues.updateComment({
      owner: params.owner,
      repo: params.repo,
      comment_id: existing.id,
      body: payload,
    });
    if (core) core.info(`updated comment ${existing.id}`);
    return { action: 'updated', id: existing.id };
  }
  const created = await github.rest.issues.createComment({ ...params, body: payload });
  if (core) core.info(`created comment ${created.data.id}`);
  return { action: 'created', id: created.data.id };
}

module.exports = upsertComment;
module.exports.MARKER = MARKER;
