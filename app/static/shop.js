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

  function initApp() {
    initFlavorEditor();
    initToast();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initApp);
  } else {
    initApp();
  }
})();
