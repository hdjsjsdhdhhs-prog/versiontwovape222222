(function () {
  function initFlavorEditor() {
    document.querySelectorAll(".flavor-editor").forEach(function (editor) {
      if (editor.dataset.flavorEditorReady === "1") return;
      var list = editor.querySelector("[data-flavor-list]");
      var button = editor.querySelector("[data-add-flavor]");
      var template = editor.querySelector("[data-flavor-row-template]");
      if (!list || !button || !template) return;
      editor.dataset.flavorEditorReady = "1";

      button.addEventListener("click", function () {
        var fragment = template.content.cloneNode(true);
        var row = fragment.querySelector(".flavor-row");
        if (!row) return;
        list.appendChild(fragment);
        var nameInput = row.querySelector("input[name='flavor_name']");
        if (nameInput) nameInput.focus();
      });

      list.addEventListener("click", function (event) {
        var target = event.target;
        if (!target || !target.matches(".remove-flavor-button")) return;
        var row = target.closest(".flavor-row");
        if (row) row.remove();
      });
    });
  }

  function initToast() {
    document.querySelectorAll("[data-toast]").forEach(function (toast) {
      window.setTimeout(function () {
        toast.classList.add("hide");
      }, 3200);
    });
  }

  function initCategoryFilter() {
    document.querySelectorAll("[data-category-filter]").forEach(function (filter) {
      if (filter.dataset.categoryFilterReady === "1") return;
      var buttons = Array.prototype.slice.call(filter.querySelectorAll("[data-category-target]"));
      var panels = Array.prototype.slice.call(filter.querySelectorAll("[data-category-panel]"));
      if (!buttons.length || !panels.length) return;
      filter.dataset.categoryFilterReady = "1";

      function setActive(categoryId) {
        buttons.forEach(function (button) {
          var isActive = button.dataset.categoryTarget === categoryId;
          button.classList.toggle("active", isActive);
          button.setAttribute("aria-selected", isActive ? "true" : "false");
        });

        panels.forEach(function (panel) {
          var isActive = panel.dataset.categoryPanel === categoryId;
          panel.classList.toggle("active", isActive);
          panel.hidden = !isActive;
        });
      }

      buttons.forEach(function (button) {
        button.addEventListener("click", function () {
          setActive(button.dataset.categoryTarget);
        });
      });

      var activeButton = null;
      buttons.forEach(function (button) {
        if (!activeButton && button.classList.contains("active")) {
          activeButton = button;
        }
      });
      setActive((activeButton || buttons[0]).dataset.categoryTarget);
    });
  }

  function initCartBadgeAnimation() {
    var nav = document.querySelector(".bottom-nav");
    if (!nav) return;
    var badge = nav.querySelector("[data-cart-count]");
    var currentCount = badge ? parseInt(badge.dataset.cartCount || badge.textContent || "0", 10) : 0;
    if (isNaN(currentCount)) currentCount = 0;

    try {
      var storageKey = "shopCartCount";
      var previousValue = window.localStorage.getItem(storageKey);
      var previousCount = previousValue === null ? null : parseInt(previousValue, 10);
      if (badge && previousCount !== null && currentCount > previousCount) {
        badge.classList.add("bump");
        window.setTimeout(function () {
          badge.classList.remove("bump");
        }, 260);
      }
      window.localStorage.setItem(storageKey, String(currentCount));
    } catch (_error) {
      return;
    }
  }

  function initApp() {
    initFlavorEditor();
    initToast();
    initCategoryFilter();
    initCartBadgeAnimation();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initApp);
  } else {
    initApp();
  }
})();
