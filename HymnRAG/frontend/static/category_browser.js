//성가책 변경 시 카테고리 불러오기
//카테고리 버튼 생성
//해당 카테고리 성가 목록 표시

window.CategoryBrowser = (() => {
  let currentBook = null;
  let selectedCategory = null;
  let requestVersion = 0;

  let categoryList;
  let categoryView;
  let recommendView;
  let categoryTitle;
  let categorySummary;
  let categoryHymns;
  let backButton;

  function showRecommend() {
    selectedCategory = null;
    requestVersion++;

    recommendView.hidden = false;
    categoryView.hidden = true;

    categoryList.querySelectorAll("button")
      .forEach(button => {
        button.classList.remove("active");
      });
  }

  function showCategory() {
    recommendView.hidden = true;
    categoryView.hidden = false;
  }

  async function setBook(bookId) {
    currentBook = bookId;
    selectedCategory = null;

    categoryList.replaceChildren();
    categoryHymns.replaceChildren();

    showRecommend();

    if (bookId) {
        categoryList.textContent = "카테고리를 불러오는 중입니다...";
    }

  const version = requestVersion;

  if (!bookId) {
    return;
  }


    try {
      const response = await fetch(
        `/api/books/${encodeURIComponent(bookId)}/categories`
      );

      if (!response.ok) {
        throw new Error("카테고리 조회 실패");
      }

      const data = await response.json();

      if (version !== requestVersion) return;

      renderCategories(data.categories || []);

    } catch (error) {
      if (version !== requestVersion) return;

      categoryList.textContent =
        "카테고리를 불러오지 못했습니다.";

      console.error(error);
    }
  }

  function renderCategories(categories) {
    categoryList.replaceChildren();

    if (categories.length === 0) {
      categoryList.textContent =
        "등록된 카테고리가 없습니다.";
      return;
    }

    categories.forEach(category => {
      const button = document.createElement("button");

      button.type = "button";
      button.className = "category-button";
      button.textContent = category;

      button.addEventListener("click", () => {
        selectCategory(category, button);
      });

      categoryList.appendChild(button);
    });
  }

  async function selectCategory(category, button) {
    if (!currentBook) return;

    selectedCategory = category;

    const bookId = currentBook;
    const version = ++requestVersion;

    categoryList.querySelectorAll("button")
      .forEach(item => {
        item.classList.remove("active");
      });

    button.classList.add("active");

    categoryTitle.textContent = `${category} 성가`;
    categorySummary.textContent =
      "성가 목록을 불러오는 중입니다.";

    categoryHymns.replaceChildren();

    showCategory();

    try {
      const params = new URLSearchParams({
        category: category
      });

      const response = await fetch(
        `/api/books/${encodeURIComponent(bookId)}/hymns?${params}`
      );

      if (!response.ok) {
        throw new Error("성가 목록 조회 실패");
      }

      const data = await response.json();

      if (version !== requestVersion) return;

      renderHymns(data.hymns || []);

      categorySummary.textContent =
        `총 ${data.count}곡`;

    } catch (error) {
      if (version !== requestVersion) return;

      categorySummary.textContent =
        "성가 목록을 불러오지 못했습니다.";

      console.error(error);
    }
  }

  function renderHymns(hymns) {
    categoryHymns.replaceChildren();

    if (hymns.length === 0) {
      categoryHymns.textContent =
        "등록된 성가가 없습니다.";
      return;
    }

    const fragment = document.createDocumentFragment();

    hymns.forEach(hymn => {
      const row = document.createElement("div");
      row.className = "category-hymn-row";

      const number = document.createElement("span");
      number.className = "hymn-number";
      number.textContent = hymn.number ?? "-";

      const title = document.createElement("span");
      title.className = "hymn-title";
      title.textContent = hymn.title || "제목 없음";

      row.append(number, title);
      fragment.appendChild(row);
    });

    categoryHymns.appendChild(fragment);
  }

  function init() {
    categoryList = document.querySelector("#categoryList");
    categoryView = document.querySelector("#categoryView");
    recommendView = document.querySelector("#recommendView");
    categoryTitle = document.querySelector("#categoryTitle");
    categorySummary = document.querySelector("#categorySummary");
    categoryHymns = document.querySelector("#categoryHymns");
    backButton = document.querySelector("#backToRecommend");

    backButton.addEventListener("click", showRecommend);

    showRecommend();
  }

  return {
    init,
    setBook,
    showRecommend
  };
})();