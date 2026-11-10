import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const catalog = JSON.parse(
  fs.readFileSync(new URL('../data/catalog.json', import.meta.url), 'utf8'),
);

function collectKeys(value, keys = []) {
  if (Array.isArray(value)) {
    value.forEach((item) => collectKeys(item, keys));
  } else if (value && typeof value === 'object') {
    for (const [key, child] of Object.entries(value)) {
      keys.push(key);
      collectKeys(child, keys);
    }
  }
  return keys;
}

test('catalog contains updates, courses, lessons and files', () => {
  assert.match(catalog.updated_at, /^\d{4}-\d{2}-\d{2}$/);
  assert(catalog.whats_new.length > 0);
  assert(catalog.courses.length > 0);
  assert(
    catalog.courses.every(
      (course) =>
        course.name &&
        course.term &&
        course.lessons.length > 0 &&
        course.lessons.every(
          (lesson) => lesson.name && Array.isArray(lesson.files),
        ),
    ),
  );
});

test('public catalog excludes identifiers, locations and outbound links', () => {
  const forbiddenKey =
    /(?:url|path|owner|email|account|file_id|folder_id|system_id|mime|parent_id)/i;
  assert.equal(
    collectKeys(catalog).some((key) => forbiddenKey.test(key)),
    false,
  );
});

test('public site has no import or file-management controls', () => {
  const runtime = ['../index.html', '../app.mjs']
    .map((file) => fs.readFileSync(new URL(file, import.meta.url), 'utf8'))
    .join('\n');
  const forbiddenText =
    /(?:JSONを読み込|アップロード|ファイル管理|フォルダー構成|詳細を表示|外部リンク|download|data-action="import")/i;
  assert.equal(forbiddenText.test(runtime), false);
});

test('separate character layers point at the update list', () => {
  const html = fs.readFileSync(
    new URL('../index.html', import.meta.url),
    'utf8',
  );
  assert.match(html, /src="\.\/assets\/birdman-left\.png"/);
  assert.match(html, /src="\.\/assets\/birdman-right\.png"/);
  assert.match(html, /<div class="whats-new-scene">[\s\S]*<div class="updates"/);
  for (const file of ['birdman-left.png', 'birdman-right.png']) {
    assert.equal(fs.existsSync(new URL(`../assets/${file}`, import.meta.url)), true);
  }
});
