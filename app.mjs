const catalogPath = './data/catalog.json';

const elements = {
  courseCount: document.querySelector('#courseCount'),
  fileCount: document.querySelector('#fileCount'),
  updatedAt: document.querySelector('#updatedAt'),
  updates: document.querySelector('#updates'),
  courseList: document.querySelector('#courseList'),
};

function formatDate(value) {
  const date = new Date(`${value}T00:00:00+09:00`);
  if (!Number.isFinite(date.getTime())) return value;
  return new Intl.DateTimeFormat('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

function countFiles(courses) {
  return courses.reduce(
    (courseTotal, course) =>
      courseTotal +
      course.lessons.reduce(
        (lessonTotal, lesson) => lessonTotal + lesson.files.length,
        0,
      ),
    0,
  );
}

function renderUpdates(updates) {
  elements.updates.replaceChildren();

  for (const update of updates) {
    const item = document.createElement('article');
    item.className = 'update-item';

    const time = document.createElement('time');
    time.dateTime = update.date;
    time.textContent = formatDate(update.date);

    const title = document.createElement('h3');
    title.textContent = update.title;

    const description = document.createElement('p');
    description.textContent = update.description;

    item.append(time, title, description);
    elements.updates.append(item);
  }
}

function renderCourses(courses) {
  elements.courseList.replaceChildren();

  courses.forEach((course, index) => {
    const card = document.createElement('details');
    card.className = 'course-card';
    card.open = index === 0;

    const summary = document.createElement('summary');
    const nameWrap = document.createElement('span');
    nameWrap.className = 'course-name';

    const name = document.createElement('strong');
    name.textContent = course.name;
    const term = document.createElement('small');
    term.textContent = course.term;
    nameWrap.append(name, term);

    const files = countFiles([course]);
    const count = document.createElement('span');
    count.className = 'course-count';
    count.textContent = `${files} files`;

    const chevron = document.createElement('span');
    chevron.className = 'course-chevron';
    chevron.setAttribute('aria-hidden', 'true');
    chevron.textContent = '+';

    summary.append(nameWrap, count, chevron);

    const body = document.createElement('div');
    body.className = 'course-body';

    for (const lesson of course.lessons) {
      const lessonBlock = document.createElement('section');
      lessonBlock.className = 'lesson';

      const lessonName = document.createElement('h3');
      lessonName.textContent = lesson.name;

      const fileList = document.createElement('ul');
      fileList.className = 'file-list';

      for (const file of lesson.files) {
        const listItem = document.createElement('li');
        listItem.textContent = file;
        fileList.append(listItem);
      }

      lessonBlock.append(lessonName, fileList);
      body.append(lessonBlock);
    }

    card.append(summary, body);
    elements.courseList.append(card);
  });
}

function validateCatalog(catalog) {
  if (
    !catalog ||
    typeof catalog.updated_at !== 'string' ||
    !Array.isArray(catalog.whats_new) ||
    !Array.isArray(catalog.courses)
  ) {
    throw new Error('Invalid catalog');
  }
}

async function loadCatalog() {
  try {
    const response = await fetch(catalogPath, { cache: 'no-store' });
    if (!response.ok) throw new Error('Catalog unavailable');

    const catalog = await response.json();
    validateCatalog(catalog);

    elements.courseCount.textContent = catalog.courses.length;
    elements.fileCount.textContent = countFiles(catalog.courses);
    elements.updatedAt.textContent = formatDate(catalog.updated_at);

    renderUpdates(catalog.whats_new);
    renderCourses(catalog.courses);
  } catch {
    const message = document.createElement('p');
    message.className = 'error-message';
    message.textContent = '資料一覧を読み込めませんでした。';
    elements.updates.replaceChildren(message.cloneNode(true));
    elements.courseList.replaceChildren(message);
  }
}

loadCatalog();
