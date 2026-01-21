/* ========== */
/* Temha */
(function () {
  // Body
  document.body.addEventListener("click", (event) => {
    if (
      !event.target.closest(".dropset-area") &&
      !event.target.closest(".selectset-area")
    ) {
      document
        .querySelectorAll(".dropset-area")
        .forEach((element) => element.classList.remove("active"));
      document
        .querySelectorAll(".selectset-area")
        .forEach((element) => element.classList.remove("active"));
    }
  });

  // Header
  document.body.addEventListener("click", (e) => {
    const link = e.target.closest(".header-gnbitem a, .fullmenu-gnbitem a");
    if (!link) return;
    const targetID = link.getAttribute("href");
    if (targetID && targetID.startsWith("#")) {
      e.preventDefault();
      const targetEl = document.querySelector(targetID);
      if (!targetEl) return;
      gsap.to(window, {
        duration: 1,
        scrollTo: { y: targetEl },
        ease: "power1.inOut",
      });
    }
  });

  // Videoset
  const videosetButtons = document.querySelectorAll(".videoset-play");
  videosetButtons.forEach((buttonElement) => {
    const clickEventHandler = (event) => {
      const buttonElement = event.target
        .closest(".videoset")
        .querySelector(".videoset-video");
      const buttonGrandParent = event.target.closest(".videoset");
      buttonElement.play();
      buttonGrandParent.classList.add("active");
      buttonElement.addEventListener("click", () => {
        buttonElement.pause();
        buttonGrandParent.classList.remove("active");
      });
    };
    buttonElement.removeEventListener("click", clickEventHandler);
    buttonElement.addEventListener("click", clickEventHandler);
  });

  // Inputset
  const inputsetElements = document.querySelectorAll(".inputset-textarea");
  inputsetElements.forEach((inputsetElement) => {
    inputsetElement.addEventListener("keyup", () => {
      const inputsetText = inputsetElement.value;
      const inputsetCount = inputsetElement
        .closest(".inputset")
        .querySelector(".inputset-count");
      if (inputsetText.length === 0 || inputsetText === "") {
        inputsetCount.textContent = "0";
      } else {
        inputsetCount.textContent = inputsetText.length;
      }
      if (inputsetText.length > 4000) {
        inputsetElement.value = inputsetText.substring(0, 4000);
      }
    });
  });

  // Inputset Password
  const inputsetPasswordElements =
    document.querySelectorAll(".inputset-password");
  inputsetPasswordElements.forEach((inputsetPasswordElement) => {
    const passwordInput =
      inputsetPasswordElement.querySelector(".inputset-input");
    const passwordHideBtn =
      inputsetPasswordElement.querySelector(".password-hide-btn");
    const passwordShowBtn =
      inputsetPasswordElement.querySelector(".password-show-btn");
    if (inputsetPasswordElement.classList.contains("password-hide")) {
      passwordShowBtn.style.display = "none";
      passwordHideBtn.style.display = "inline-block";
      passwordInput.type = "password";
    }
    passwordHideBtn.addEventListener("click", () => {
      inputsetPasswordElement.classList.remove("password-hide");
      inputsetPasswordElement.classList.add("password-show");
      passwordInput.type = "text";
      passwordShowBtn.style.display = "inline-block";
      passwordHideBtn.style.display = "none";
    });
    passwordShowBtn.addEventListener("click", () => {
      inputsetPasswordElement.classList.remove("password-show");
      inputsetPasswordElement.classList.add("password-hide");
      passwordInput.type = "password";
      passwordShowBtn.style.display = "none";
      passwordHideBtn.style.display = "inline-block";
    });
  });

  // Inputset Type Date
  const inputsetDateElements = document.querySelectorAll(
    ".inputset-date input[type='date']"
  );
  inputsetDateElements.forEach((inputsetDateElement) => {
    if (inputsetDateElement.value) {
      inputsetDateElement.classList.add("has-value");
    }
    inputsetDateElement.addEventListener("input", () => {
      if (inputsetDateElement.value) {
        inputsetDateElement.classList.add("has-value");
      } else {
        inputsetDateElement.classList.remove("has-value");
      }
    });
    inputsetDateElement.addEventListener("change", () => {
      if (inputsetDateElement.value) {
        inputsetDateElement.classList.add("has-value");
      } else {
        inputsetDateElement.classList.remove("has-value");
      }
    });
  });

  // Inputset Type Time
  const inputsetTimeElements = document.querySelectorAll(
    ".inputset-time input[type='time']"
  );
  inputsetTimeElements.forEach((inputsetTimeElement) => {
    if (inputsetTimeElement.value) {
      inputsetTimeElement.classList.add("has-value");
    }
    inputsetTimeElement.addEventListener("input", () => {
      if (inputsetTimeElement.value) {
        inputsetTimeElement.classList.add("has-value");
      } else {
        inputsetTimeElement.classList.remove("has-value");
      }
    });
    inputsetTimeElement.addEventListener("change", () => {
      if (inputsetTimeElement.value) {
        inputsetTimeElement.classList.add("has-value");
      } else {
        inputsetTimeElement.classList.remove("has-value");
      }
    });
  });

  // Inputset Floating Label
  const floatingInputElements = document.querySelectorAll(
    ".inputset-floating .form-control"
  );
  floatingInputElements.forEach((floatingInputElement) => {
    const label = floatingInputElement
      .closest(".inputset-floating")
      .querySelector("label");
    if (floatingInputElement.value.length > 0) {
      label.classList.add("label-floating");
    }
    floatingInputElement.addEventListener("focus", () => {
      label.classList.add("label-floating");
    });
    floatingInputElement.addEventListener("blur", () => {
      if (floatingInputElement.value.length === 0) {
        label.classList.remove("label-floating");
      }
    });
    floatingInputElement.addEventListener("input", () => {
      if (floatingInputElement.value.length > 0) {
        label.classList.add("label-floating");
      } else {
        label.classList.remove("label-floating");
      }
    });
  });

  // Fileset
  const filesetElements = document.querySelectorAll(".fileset");
  filesetElements.forEach((filesetElement) => {
    const filesetInput = filesetElement.querySelector(".fileset-input");
    const filesetCancel = filesetElement.querySelector(".fileset-cancel");
    filesetInput.addEventListener("change", () => {
      filesetInput.classList.add("active");
      filesetCancel.style.display = "block";
    });
    filesetCancel.addEventListener("click", () => {
      filesetInput.value = "";
      filesetInput.classList.remove("active");
      filesetCancel.style.display = "none";
    });
  });

  // Tabset
  const tabsetLink = document.querySelectorAll(".tabset-link");
  tabsetLink.forEach((buttonElement) => {
    const clickEventHandler = (event) => {
      event.stopPropagation();
      const button = event.target.closest(".tabset-link");
      const buttonGrandParent = button.closest(".tabset-list");
      const buttonParent = button.closest(".tabset-item");
      const buttonParentSiblings = getSiblings(buttonGrandParent, buttonParent);
      const buttonParentIndex = getIndex(buttonParent);
      const itemTabsetContainer = button
        .closest(".tabset")
        .querySelector(".tabset-container");
      buttonParentSiblings.forEach((siblingElement) => {
        siblingElement.querySelector(".tabset-link").classList.remove("active");
      });
      button.classList.add("active");
      if (itemTabsetContainer) {
        itemTabsetContainer
          .querySelectorAll(".tabset-cont")
          .forEach((contElement) => {
            const contElementIndex = getIndex(contElement);
            contElement.classList.remove("active");
            if (contElementIndex === buttonParentIndex) {
              contElement.classList.add("active");
            }
          });
      }
    };
    buttonElement.removeEventListener("click", clickEventHandler);
    buttonElement.addEventListener("click", clickEventHandler);
  });

  // Selectset
  const selectsetToggle = document.querySelectorAll(".selectset-toggle");
  const selectsetLink = document.querySelectorAll(".selectset-link");
  selectsetToggle.forEach((buttonElement) => {
    const clickEventHandler = (event) => {
      // event.stopPropagation();
      const button = event.target.closest(".selectset-toggle");
      const buttonParent = button.closest(".selectset-area");
      buttonParent.classList.toggle("active");
    };
    buttonElement.removeEventListener("click", clickEventHandler);
    buttonElement.addEventListener("click", clickEventHandler);
  });
  selectsetLink.forEach((buttonElement) => {
    const clickEventHandler = (event) => {
      // event.stopPropagation();
      const button = event.target.closest(".selectset-link");
      const buttonText = button.querySelector("span").innerHTML;
      const buttonGrandParent = button.closest(".selectset-list");
      const buttonParent = button.closest(".selectset-item");
      const buttonParentSiblings = getSiblings(buttonGrandParent, buttonParent);
      const buttonSelectsetToggle = button
        .closest(".selectset-area")
        .querySelector(".selectset-toggle");
      buttonParentSiblings.forEach((siblingElement) => {
        siblingElement.querySelector(".selectset-link").classList.remove("on");
      });
      button.classList.toggle("on");
      buttonSelectsetToggle.querySelector("span").innerHTML = buttonText;
      button.closest(".selectset-area").classList.remove("active");
    };
    buttonElement.removeEventListener("click", clickEventHandler);
    buttonElement.addEventListener("click", clickEventHandler);
  });

  // Dropset
  const dropsetToggle = document.querySelectorAll(".dropset-toggle");
  dropsetToggle.forEach((buttonElement) => {
    const clickEventHandler = (event) => {
      // event.stopPropagation();
      const button = event.target.closest(".dropset-toggle");
      const buttonParent = button.closest(".dropset-area");
      buttonParent.classList.toggle("active");
    };
    buttonElement.removeEventListener("click", clickEventHandler);
    buttonElement.addEventListener("click", clickEventHandler);
  });

  // Accordset
  const accordsetButton = document.querySelectorAll(".accordset-button");
  accordsetButton.forEach((buttonElement) => {
    const clickEventHandler = (event) => {
      const button = event.target.closest(".accordset-button");
      const buttonGrandParent = button.closest(".accordset");
      const buttonParent = button.closest(".accordset-item");
      const buttonParentSiblings = getSiblings(buttonGrandParent, buttonParent);
      buttonParentSiblings.forEach((siblingElement) => {
        siblingElement.classList.remove("active");
        $(siblingElement).find(".accordset-body").stop().slideUp();
      });
      buttonParent.classList.toggle("active");
      $(buttonParent).find(".accordset-body").stop().slideToggle();
    };
    buttonElement.removeEventListener("click", clickEventHandler);
    buttonElement.addEventListener("click", clickEventHandler);
  });

  // Toast
  const toastClose = document.querySelectorAll(".toastset-close");
  toastClose.forEach((buttonElement) => {
    const clickEventHandler = (event) => {
      const button = event.target.closest(".toastset-close");
      const buttonGrandParent = button.closest(".toastset");
      buttonGrandParent.remove();
    };
    buttonElement.removeEventListener("click", clickEventHandler);
    buttonElement.addEventListener("click", clickEventHandler);
  });

  // Tooltip
  const btnTooltipset = document.querySelectorAll(".btn-tooltipset");
  if (btnTooltipset) {
    btnTooltipset.forEach((element) => {
      const mouseroverEventHandler = () => {
        const data = element.dataset;
        const type = data.tooltipType;
        const color = data.tooltipColor;
        const place = data.tooltipPlace;
        const title = data.tooltipTitle;
        const text = data.tooltipText;
        const image = data.tooltipImage;
        const position = element.getBoundingClientRect();
        const width = position.width;
        const height = position.height;
        const startX = position.x;
        const startY = position.y;
        const midX = startX + width / 2;
        const midY = startY + height / 2;
        const endX = position.right;
        const endY = position.bottom;
        let html = "";
        if (type === "guide") {
          html += `<div class="tooltipset tooltipset-title tooltipset-arrow tooltipset-${color} tooltipset-${place}">`;
        }
        if (type === "tip") {
          html += `<div class="tooltipset tooltipset-arrow tooltipset-${color} tooltipset-${place}">`;
        }
        if (type === "name") {
          html += `<div class="tooltipset tooltipset-name tooltipset-${color} tooltipset-${place}">`;
        }
        if (type === "image") {
          html += `<div class="tooltipset tooltipset-name tooltipset-${color} tooltipset-${place}">`;
        }
        if (type === "bubble") {
          html += `<div class="tooltipset tooltipset-arrow tooltipset-${color} tooltipset-${place} tooltipset-dist">`;
        }
        if (type === "round") {
          html += `<div class="tooltipset tooltipset-arrow tooltipset-${color} tooltipset-${place} tooltipset-round">`;
        }
        html += `<div class="tooltipset-container">`;
        if (type === "image") {
          html += `<div class="tooltipset-group tooltipset-img-group">`;
          html += `<figure class="tooltipset-figure">`;
          html += `<img class="tooltipset-img" src="${image}" alt="${text}">`;
          html += `</figure>`;
        } else {
          html += `<div class="tooltipset-group">`;
        }
        if (type === "guide") {
          html += `<h2 class="tooltipset-tit">${title}</h2>`;
        }
        html += `<p class="tooltipset-text">${text}</p>`;
        html += `</div>`;
        html += `</div>`;
        html += `</div>`;
        const dom = new DOMParser().parseFromString(html, "text/html");
        document.body.append(dom.body.querySelector(".tooltipset"));
        const tooltipset = document.querySelector(".tooltipset");
        const tooltipsetClassList = [...tooltipset.classList];
        const tooltipsetStyle = tooltipset.style;
        if (tooltipsetClassList.includes("tooltipset-top")) {
          tooltipsetStyle.left = midX + "px";
          tooltipsetStyle.top = startY - 5 + "px";
          tooltipsetStyle.transform = "translate(-50%, calc(-100% - 10px))";
        } else if (tooltipsetClassList.includes("tooltipset-bottom")) {
          tooltipsetStyle.left = midX + "px";
          tooltipsetStyle.top = endY + 5 + "px";
          tooltipsetStyle.transform = "translate(-50%, 10px)";
        } else if (tooltipsetClassList.includes("tooltipset-left")) {
          tooltipsetStyle.left = startX - 5 + "px";
          tooltipsetStyle.top = midY + "px";
          tooltipsetStyle.transform = "translate(calc(-100% - 10px), -50%)";
        } else if (tooltipsetClassList.includes("tooltipset-right")) {
          tooltipsetStyle.left = endX + 5 + "px";
          tooltipsetStyle.top = midY + "px";
          tooltipsetStyle.transform = "translate(10px, -50%)";
        }
        document
          .querySelectorAll(".tooltipset")
          .forEach((element, index) => index !== 0 && element.remove());
      };
      const clickEventHandler = () =>
        document
          .querySelectorAll(".tooltipset")
          .forEach((element) => element.remove());
      element.removeEventListener("mouseover", mouseroverEventHandler);
      element.addEventListener("mouseover", mouseroverEventHandler);
      element.removeEventListener("click", clickEventHandler);
      element.addEventListener("click", clickEventHandler);
    });
  }
  const mouseoutEventHandler = () =>
    document
      .querySelectorAll(".tooltipset")
      .forEach((element) => element.remove());
  document.removeEventListener("mouseout", mouseoutEventHandler);
  document.addEventListener("mouseout", mouseoutEventHandler);

  // Modalset
  const btnModalset = document.querySelectorAll(".modalset");
  const btnModalsetOpen = document.querySelectorAll(".modalset-open-btn");
  const btnModalsetClose = document.querySelectorAll(
    "[data-modal-close='modalset']"
  );
  const toggleModal = (modalId, isOpen) => {
    const modals = document.querySelectorAll(".modalset");
    modals.forEach((modal) => modal.classList.remove("modalset-active"));
    if (isOpen) {
      document.body.style.overflow = "hidden";
      const targetModal = document.querySelector(
        `.modalset[data-modal-id="${modalId}"]`
      );
      if (targetModal) {
        targetModal.classList.add("modalset-active");
        const video = targetModal.querySelector("video");
        if (video) {
          video
            .play()
            .catch((error) => console.log("자동 재생 차단됨:", error));
        }
      }
    }
  };
  btnModalsetOpen.forEach((button) => {
    button.addEventListener("click", (event) => {
      const targetModalId =
        event.currentTarget.getAttribute("data-modal-target");
      toggleModal(targetModalId, true);
    });
  });
  btnModalsetClose.forEach((button) => {
    button.addEventListener("click", (event) => {
      document.body.removeAttribute("style");
      const modalToClose = event.target.closest(".modalset");
      if (modalToClose) {
        modalToClose.classList.remove("modalset-active");
        const video = modalToClose.querySelector("video");
        if (video) {
          video.pause();
          video.currentTime = 0;
        }
        const iframe = modalToClose.querySelector("iframe");
        if (iframe) {
          const src = iframe.src;
          iframe.src = "";
          setTimeout(() => {
            iframe.src = src;
          }, 100);
        }
      }
    });
  });
  btnModalset.forEach((modal) => {
    modal.addEventListener("click", (event) => {
      if (event.target === modal) {
        document.body.removeAttribute("style");
        modal.classList.remove("modalset-active");
        const video = modal.querySelector("video");
        if (video) {
          video.pause();
          video.currentTime = 0;
        }
        const iframe = modalToClose.querySelector("iframe");
        if (iframe) {
          const src = iframe.src;
          iframe.src = "";
          setTimeout(() => {
            iframe.src = src;
          }, 100);
        }
      }
    });
  });

  // Function
  function getSiblings(parent, element) {
    return [...parent.children].filter((item) => item !== element);
  }
  function getIndex(element) {
    return [...element.parentNode.children].indexOf(element);
  }
})();
