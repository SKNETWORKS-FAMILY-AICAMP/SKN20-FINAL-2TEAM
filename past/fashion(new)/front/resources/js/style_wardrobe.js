/* wellness-N1 [ZIMKM77Ic3] */
(function() {
  $(function() {
    $(".wellness-N1[id=\'ZIMKM77Ic3\']").each(function() {
      const $block = $(this);
      let isMobileMenuInitialized = false;
      let isDesktopMenuInitialized = false;
      // 모바일 메뉴 초기화
      function initMobileMenu() {
        if (isMobileMenuInitialized) return;
        const $btnMomenu = $block.find(".btn-momenu");
        $btnMomenu.off("click").on("click", function() {
          if ($block.hasClass("block-active")) {
            $block.removeClass("block-active");
          } else {
            $block.addClass("block-active");
          }
          $block.find(".header-gnbitem").removeClass("item-active");
          $block.find(".header-sublist").removeAttr("style");
        });
        // header-gnbitem 클릭 이벤트
        $block.find(".header-gnbitem").each(function() {
          const $this = $(this);
          const $thisLink = $this.find(".header-gnblink");
          const $sublist = $this.find(".header-sublist");
          if ($sublist.length) {
            $thisLink.off("click").on("click", function(event) {
              event.preventDefault();
              const $clickedItem = $(this).parents(".header-gnbitem");
              if (!$clickedItem.hasClass("item-active")) {
                $block.find(".header-gnbitem").removeClass("item-active");
                $block.find(".header-sublist").stop().slideUp(300);
              }
              $clickedItem.toggleClass("item-active");
              $sublist.stop().slideToggle(300);
            });
          }
        });
        isMobileMenuInitialized = true;
      }
      // 데스크탑 메뉴 초기화
      function initDesktopMenu() {
        if (isDesktopMenuInitialized) return;
        $block.find(".header-gnbitem").each(function() {
          const $this = $(this);
          const $thisLink = $this.find(".header-gnblink");
          $thisLink.off("click");
        });
        isDesktopMenuInitialized = true;
      }
      // 해상도에 따른 메뉴 처리
      function handleResize() {
        if (window.innerWidth <= 992) {
          if (!isMobileMenuInitialized) {
            initMobileMenu();
          }
          isDesktopMenuInitialized = false;
        } else {
          if (!isDesktopMenuInitialized) {
            initDesktopMenu();
          }
          isMobileMenuInitialized = false;
        }
      }
      // 스크롤 시 메뉴 처리
      function handleScroll() {
        const $headerTop = $block.find(".header-top");
        if ($headerTop.length) {
          $block.addClass("top-menu-active");
        }
        if ($(window).scrollTop() === 0) {
          $block.addClass("header-top-active");
        }
        $(window).scroll(function() {
          if ($(window).scrollTop() > 0) {
            $block.removeClass("header-top-active");
          } else {
            $block.addClass("header-top-active");
          }
        });
      }
      handleScroll();
      // 전체 메뉴 열기/닫기 처리
      function handleFullMenu() {
        $block.find(".btn-allmenu").on("click", function() {
          $block.find(".header-fullmenu").addClass("fullmenu-active");
        });
        $block.find(".fullmenu-close").on("click", function() {
          $block.find(".header-fullmenu").removeClass("fullmenu-active");
        });
        $block.find(".fullmenu-gnbitem").each(function() {
          const $this = $(this);
          $this.on("mouseover", function() {
            if (window.innerWidth > 992) {
              $this.find(".fullmenu-gnblink").addClass("on");
            }
          });
          $this.on("mouseout", function() {
            if (window.innerWidth > 992) {
              $this.find(".fullmenu-gnblink").removeClass("on");
            }
          });
        });
      }
      handleFullMenu();
      // 리사이즈 시마다 메뉴 동작 초기화
      $(window).on("resize", function() {
        handleResize();
      });
      handleResize();
    });
  });
})();
/* wellness-N1 [QRMKM79mts] */
(function() {
  $(function() {
    $(".wellness-N1[id=\'QRMKM79mts\']").each(function() {
      const $block = $(this);
      let isMobileMenuInitialized = false;
      let isDesktopMenuInitialized = false;
      // 모바일 메뉴 초기화
      function initMobileMenu() {
        if (isMobileMenuInitialized) return;
        const $btnMomenu = $block.find(".btn-momenu");
        $btnMomenu.off("click").on("click", function() {
          if ($block.hasClass("block-active")) {
            $block.removeClass("block-active");
          } else {
            $block.addClass("block-active");
          }
          $block.find(".header-gnbitem").removeClass("item-active");
          $block.find(".header-sublist").removeAttr("style");
        });
        // header-gnbitem 클릭 이벤트
        $block.find(".header-gnbitem").each(function() {
          const $this = $(this);
          const $thisLink = $this.find(".header-gnblink");
          const $sublist = $this.find(".header-sublist");
          if ($sublist.length) {
            $thisLink.off("click").on("click", function(event) {
              event.preventDefault();
              const $clickedItem = $(this).parents(".header-gnbitem");
              if (!$clickedItem.hasClass("item-active")) {
                $block.find(".header-gnbitem").removeClass("item-active");
                $block.find(".header-sublist").stop().slideUp(300);
              }
              $clickedItem.toggleClass("item-active");
              $sublist.stop().slideToggle(300);
            });
          }
        });
        isMobileMenuInitialized = true;
      }
      // 데스크탑 메뉴 초기화
      function initDesktopMenu() {
        if (isDesktopMenuInitialized) return;
        $block.find(".header-gnbitem").each(function() {
          const $this = $(this);
          const $thisLink = $this.find(".header-gnblink");
          $thisLink.off("click");
        });
        isDesktopMenuInitialized = true;
      }
      // 해상도에 따른 메뉴 처리
      function handleResize() {
        if (window.innerWidth <= 992) {
          if (!isMobileMenuInitialized) {
            initMobileMenu();
          }
          isDesktopMenuInitialized = false;
        } else {
          if (!isDesktopMenuInitialized) {
            initDesktopMenu();
          }
          isMobileMenuInitialized = false;
        }
      }
      // 스크롤 시 메뉴 처리
      function handleScroll() {
        const $headerTop = $block.find(".header-top");
        if ($headerTop.length) {
          $block.addClass("top-menu-active");
        }
        if ($(window).scrollTop() === 0) {
          $block.addClass("header-top-active");
        }
        $(window).scroll(function() {
          if ($(window).scrollTop() > 0) {
            $block.removeClass("header-top-active");
          } else {
            $block.addClass("header-top-active");
          }
        });
      }
      handleScroll();
      // 전체 메뉴 열기/닫기 처리
      function handleFullMenu() {
        $block.find(".btn-allmenu").on("click", function() {
          $block.find(".header-fullmenu").addClass("fullmenu-active");
        });
        $block.find(".fullmenu-close").on("click", function() {
          $block.find(".header-fullmenu").removeClass("fullmenu-active");
        });
        $block.find(".fullmenu-gnbitem").each(function() {
          const $this = $(this);
          $this.on("mouseover", function() {
            if (window.innerWidth > 992) {
              $this.find(".fullmenu-gnblink").addClass("on");
            }
          });
          $this.on("mouseout", function() {
            if (window.innerWidth > 992) {
              $this.find(".fullmenu-gnblink").removeClass("on");
            }
          });
        });
      }
      handleFullMenu();
      // 리사이즈 시마다 메뉴 동작 초기화
      $(window).on("resize", function() {
        handleResize();
      });
      handleResize();
    });
  });
})();
/* wellness-N4 [GjMKm77IgX] */
(function() {
  $(function() {
    $(".wellness-N4[id=\'GjMKm77IgX\']").each(function() {
      const $block = $(this);
      const swiper = new Swiper(".wellness-N4[id=\'GjMKm77IgX\'] .swiper", {
        speed: 600,
        parallax: true,
        loop: true,
        autoplay: {
          delay: 5000,
          disableOnInteraction: false,
        },
        pagination: {
          el: ".wellness-N4[id=\'GjMKm77IgX\'] .swiper .swiper-pagination",
          clickable: true,
        },
        breakpoints: {
          992: {
            threshold: 100,
          },
        },
        on: {
          init: function() {
            const totalSlides = this.slides.filter(
              (slide) => !slide.classList.contains("swiper-slide-duplicate")
            ).length;
            $block.find(".all").text(totalSlides.toString().padStart(2, "0"));
          },
          slideChange: function() {
            const currentIndex = this.realIndex + 1;
            $block
              .find(".current")
              .text(currentIndex.toString().padStart(2, "0"));
          },
        },
      });
      // Swiper Play, Pause Button
      const pauseButton = $block.find(".swiper-button-pause");
      const playButton = $block.find(".swiper-button-play");
      playButton.hide();
      pauseButton.show();
      pauseButton.on("click", function() {
        swiper.autoplay.stop();
        playButton.show();
        pauseButton.hide();
      });
      playButton.on("click", function() {
        swiper.autoplay.start();
        playButton.hide();
        pauseButton.show();
      });
    });
  });
})();
/* wellness-N4 [dCmkm79MTs] */
(function() {
  $(function() {
    $(".wellness-N4[id=\'dCmkm79MTs\']").each(function() {
      const $block = $(this);
      const swiper = new Swiper(".wellness-N4[id=\'dCmkm79MTs\'] .swiper", {
        speed: 600,
        parallax: true,
        loop: true,
        autoplay: {
          delay: 5000,
          disableOnInteraction: false,
        },
        pagination: {
          el: ".wellness-N4[id=\'dCmkm79MTs\'] .swiper .swiper-pagination",
          clickable: true,
        },
        breakpoints: {
          992: {
            threshold: 100,
          },
        },
        on: {
          init: function() {
            const totalSlides = this.slides.filter(
              (slide) => !slide.classList.contains("swiper-slide-duplicate")
            ).length;
            $block.find(".all").text(totalSlides.toString().padStart(2, "0"));
          },
          slideChange: function() {
            const currentIndex = this.realIndex + 1;
            $block
              .find(".current")
              .text(currentIndex.toString().padStart(2, "0"));
          },
        },
      });
      // Swiper Play, Pause Button
      const pauseButton = $block.find(".swiper-button-pause");
      const playButton = $block.find(".swiper-button-play");
      playButton.hide();
      pauseButton.show();
      pauseButton.on("click", function() {
        swiper.autoplay.stop();
        playButton.show();
        pauseButton.hide();
      });
      playButton.on("click", function() {
        swiper.autoplay.start();
        playButton.hide();
        pauseButton.show();
      });
    });
  });
})();
/* wellness-N6 [zkMkm77inC] */
(function() {
  $(function() {
    $(".wellness-N6[id=\'zkMkm77inC\']").each(function() {
      // Swiper
      const swiper = new Swiper(".wellness-N6[id=\'zkMkm77inC\'] .swiper", {
        loop: true,
        slidesPerView: "auto",
        centeredSlides: true,
        spaceBetween: 24,
        pagination: {
          el: ".wellness-N6[id=\'zkMkm77inC\'] .paging",
          type: "bullets",
          clickable: true,
        },
        navigation: {
          nextEl: ".wellness-N6[id=\'zkMkm77inC\'] .btn-next",
          prevEl: ".wellness-N6[id=\'zkMkm77inC\'] .btn-prev",
        },
        breakpoints: {
          992: {
            spaceBetween: 40,
          },
        },
      });
    });
  });
})();
/* wellness-N6 [wLmKm79Mts] */
(function() {
  $(function() {
    $(".wellness-N6[id=\'wLmKm79Mts\']").each(function() {
      // Swiper
      const swiper = new Swiper(".wellness-N6[id=\'wLmKm79Mts\'] .swiper", {
        loop: true,
        slidesPerView: "auto",
        centeredSlides: true,
        spaceBetween: 24,
        pagination: {
          el: ".wellness-N6[id=\'wLmKm79Mts\'] .paging",
          type: "bullets",
          clickable: true,
        },
        navigation: {
          nextEl: ".wellness-N6[id=\'wLmKm79Mts\'] .btn-next",
          prevEl: ".wellness-N6[id=\'wLmKm79Mts\'] .btn-prev",
        },
        breakpoints: {
          992: {
            spaceBetween: 40,
          },
        },
      });
    });
  });
})();
/* wellness-N9 [scmKM77IWu] */
(function() {
  $(function() {
    $(".wellness-N9[id=\'scmKM77IWu\']").each(function() {
      const swiper = new Swiper(".wellness-N9[id=\'scmKM77IWu\'] .swiper", {
        loop: true,
        slidesPerView: "auto",
        spaceBetween: 12,
        autoplay: {
          delay: 5000,
          disableOnInteraction: false,
        },
        pagination: {
          el: ".wellness-N9[id=\'scmKM77IWu\'] .paging",
          type: "progressbar",
          clickable: true,
        },
        navigation: {
          nextEl: ".wellness-N9[id=\'scmKM77IWu\'] .btn-next",
          prevEl: ".wellness-N9[id=\'scmKM77IWu\'] .btn-prev",
        },
        breakpoints: {
          992: {
            spaceBetween: 40,
          },
        },
      });
    });
  });
})();
/* wellness-N9 [kJmkM79mts] */
(function() {
  $(function() {
    $(".wellness-N9[id=\'kJmkM79mts\']").each(function() {
      const swiper = new Swiper(".wellness-N9[id=\'kJmkM79mts\'] .swiper", {
        loop: true,
        slidesPerView: "auto",
        spaceBetween: 12,
        autoplay: {
          delay: 5000,
          disableOnInteraction: false,
        },
        pagination: {
          el: ".wellness-N9[id=\'kJmkM79mts\'] .paging",
          type: "progressbar",
          clickable: true,
        },
        navigation: {
          nextEl: ".wellness-N9[id=\'kJmkM79mts\'] .btn-next",
          prevEl: ".wellness-N9[id=\'kJmkM79mts\'] .btn-prev",
        },
        breakpoints: {
          992: {
            spaceBetween: 40,
          },
        },
      });
    });
  });
})();
/* museum-N1 [VLMKm7hNU5] */
(function() {
  $(function() {
    $(".museum-N1[id=\'VLMKm7hNU5\']").each(function() {
      const $block = $(this);
      let isMobileMenuInitialized = false;
      let isDesktopMenuInitialized = false;
      // 모바일 메뉴 초기화
      function initMobileMenu() {
        if (isMobileMenuInitialized) return;
        const $btnMomenu = $block.find(".btn-momenu");
        $btnMomenu.off("click").on("click", function() {
          $block.toggleClass("block-active");
          $block.find(".header-gnbitem").removeClass("item-active");
          $block.find(".header-sublist").removeAttr("style");
        });
        $block.find(".header-gnbitem").each(function() {
          const $this = $(this);
          const $thisLink = $this.find(".header-gnblink");
          const $sublist = $this.find(".header-sublist");
          if ($sublist.length) {
            $thisLink.off("click").on("click", function(event) {
              event.preventDefault();
              const $clickedItem = $(this).closest(".header-gnbitem");
              if (!$clickedItem.hasClass("item-active")) {
                $block.find(".header-gnbitem").removeClass("item-active");
                $block.find(".header-sublist").stop().slideUp(300);
              }
              $clickedItem.toggleClass("item-active");
              $sublist.stop().slideToggle(300);
            });
          }
        });
        isMobileMenuInitialized = true;
      }
      // 데스크탑 메뉴 초기화
      function initDesktopMenu() {
        if (isDesktopMenuInitialized) return;
        $block.find(".header-gnbitem .header-gnblink").off("click");
        isDesktopMenuInitialized = true;
      }
      // 해상도에 따른 메뉴 처리
      function handleResize() {
        if (window.innerWidth <= 992) {
          if (!isMobileMenuInitialized) initMobileMenu();
          isDesktopMenuInitialized = false;
        } else {
          if (!isDesktopMenuInitialized) initDesktopMenu();
          isMobileMenuInitialized = false;
        }
      }
      // 스크롤 시 메뉴 처리
      function handleScroll() {
        const $headerTop = $block.find(".header-top");
        if ($headerTop.length) $block.addClass("top-menu-active");
        if ($(window).scrollTop() === 0) $block.addClass("header-top-active");
        $(window).on("scroll", function() {
          if ($(window).scrollTop() > 0) {
            $block.removeClass("header-top-active");
          } else {
            $block.addClass("header-top-active");
          }
        });
      }
      handleScroll();
      // 전체 메뉴 열기/닫기 처리
      function handleFullMenu() {
        $block.find(".btn-allmenu").on("click", function() {
          $block.find(".header-fullmenu").addClass("fullmenu-active");
        });
        $block.find(".fullmenu-close").on("click", function() {
          $block.find(".header-fullmenu").removeClass("fullmenu-active");
        });
        $block.find(".fullmenu-gnbitem").each(function() {
          const $this = $(this);
          $this.on("mouseover", function() {
            if (window.innerWidth > 992) {
              $this.find(".fullmenu-gnblink").addClass("on");
            }
          });
          $this.on("mouseout", function() {
            if (window.innerWidth > 992) {
              $this.find(".fullmenu-gnblink").removeClass("on");
            }
          });
        });
      }
      handleFullMenu();
      // 리사이즈 시마다 메뉴 동작 초기화
      $(window).on("resize", handleResize);
      handleResize();
    });
  });
})();
/* museum-N1 [FcMkm7I8W5] */
(function() {
  $(function() {
    $(".museum-N1[id=\'FcMkm7I8W5\']").each(function() {
      const $block = $(this);
      let isMobileMenuInitialized = false;
      let isDesktopMenuInitialized = false;
      // 모바일 메뉴 초기화
      function initMobileMenu() {
        if (isMobileMenuInitialized) return;
        const $btnMomenu = $block.find(".btn-momenu");
        $btnMomenu.off("click").on("click", function() {
          $block.toggleClass("block-active");
          $block.find(".header-gnbitem").removeClass("item-active");
          $block.find(".header-sublist").removeAttr("style");
        });
        $block.find(".header-gnbitem").each(function() {
          const $this = $(this);
          const $thisLink = $this.find(".header-gnblink");
          const $sublist = $this.find(".header-sublist");
          if ($sublist.length) {
            $thisLink.off("click").on("click", function(event) {
              event.preventDefault();
              const $clickedItem = $(this).closest(".header-gnbitem");
              if (!$clickedItem.hasClass("item-active")) {
                $block.find(".header-gnbitem").removeClass("item-active");
                $block.find(".header-sublist").stop().slideUp(300);
              }
              $clickedItem.toggleClass("item-active");
              $sublist.stop().slideToggle(300);
            });
          }
        });
        isMobileMenuInitialized = true;
      }
      // 데스크탑 메뉴 초기화
      function initDesktopMenu() {
        if (isDesktopMenuInitialized) return;
        $block.find(".header-gnbitem .header-gnblink").off("click");
        isDesktopMenuInitialized = true;
      }
      // 해상도에 따른 메뉴 처리
      function handleResize() {
        if (window.innerWidth <= 992) {
          if (!isMobileMenuInitialized) initMobileMenu();
          isDesktopMenuInitialized = false;
        } else {
          if (!isDesktopMenuInitialized) initDesktopMenu();
          isMobileMenuInitialized = false;
        }
      }
      // 스크롤 시 메뉴 처리
      function handleScroll() {
        const $headerTop = $block.find(".header-top");
        if ($headerTop.length) $block.addClass("top-menu-active");
        if ($(window).scrollTop() === 0) $block.addClass("header-top-active");
        $(window).on("scroll", function() {
          if ($(window).scrollTop() > 0) {
            $block.removeClass("header-top-active");
          } else {
            $block.addClass("header-top-active");
          }
        });
      }
      handleScroll();
      // 전체 메뉴 열기/닫기 처리
      function handleFullMenu() {
        $block.find(".btn-allmenu").on("click", function() {
          $block.find(".header-fullmenu").addClass("fullmenu-active");
        });
        $block.find(".fullmenu-close").on("click", function() {
          $block.find(".header-fullmenu").removeClass("fullmenu-active");
        });
        $block.find(".fullmenu-gnbitem").each(function() {
          const $this = $(this);
          $this.on("mouseover", function() {
            if (window.innerWidth > 992) {
              $this.find(".fullmenu-gnblink").addClass("on");
            }
          });
          $this.on("mouseout", function() {
            if (window.innerWidth > 992) {
              $this.find(".fullmenu-gnblink").removeClass("on");
            }
          });
        });
      }
      handleFullMenu();
      // 리사이즈 시마다 메뉴 동작 초기화
      $(window).on("resize", handleResize);
      handleResize();
    });
  });
})();
/* museum-N3 */
(function() {
  $(function() {
    $(".museum-N3[id=\'xwmKm7HnZ9\']").each(function() {
      const $block = $(this);
      // 텍스트 애니메이션
      const animateTexts = ($textset, delay = 0) => {
        const $subtit = $textset.find(".textset-subtit");
        const $tit = $textset.find(".textset-tit");
        const $desc = $textset.find(".textset-desc");
        // 초기 상태 설정
        if ($subtit.length) gsap.set($subtit[0], {
          y: 50,
          opacity: 0
        });
        if ($tit.length) gsap.set($tit[0], {
          y: 50,
          opacity: 0
        });
        if ($desc.length) gsap.set($desc[0], {
          y: 50,
          opacity: 0
        });
        // 타임라인 생성
        const tl = gsap.timeline({
          delay
        });
        // 애니메이션
        if ($subtit.length) {
          tl.to($subtit[0], {
            y: 0,
            opacity: 1,
            duration: 0.6,
            ease: "power2.out",
          });
        }
        if ($tit.length) {
          tl.to(
            $tit[0], {
              y: 0,
              opacity: 1,
              duration: 0.6,
              ease: "power2.out",
            },
            "-=0.2"
          );
        }
        if ($desc.length) {
          tl.to(
            $desc[0], {
              y: 0,
              opacity: 1,
              duration: 0.6,
              ease: "power2.out",
            },
            "-=0.2"
          );
        }
      };
      // Swiper
      const swiper = new Swiper(".museum-N3[id=\'xwmKm7HnZ9\'] .swiper", {
        loop: true,
        autoplay: {
          delay: 5000,
        },
        speed: 1500,
        effect: "fade",
        fadeEffect: {
          crossFade: true,
        },
        navigation: {
          nextEl: ".museum-N3[id=\'xwmKm7HnZ9\'] .btn-next",
          prevEl: ".museum-N3[id=\'xwmKm7HnZ9\'] .btn-prev",
        },
        breakpoints: {
          992: {
            threshold: 100,
          },
        },
        on: {
          init() {
            // 초기 로딩 시 애니메이션
            const $activeSlide = $block
              .find(".swiper-slide")
              .eq(this.activeIndex);
            const $textset = $activeSlide.find(".textset");
            if ($textset.length) {
              animateTexts($textset, 0.5);
            }
            const totalSlides = this.slides.filter(
              (slide) => !slide.classList.contains("swiper-slide-duplicate")
            ).length;
            $block.find(".total").text(totalSlides.toString().padStart(2, "0"));
          },
          slideChange() {
            const currentSlide = (this.realIndex + 1)
              .toString()
              .padStart(2, "0");
            $block.find(".curr").text(currentSlide);
            // 이전 애니메이션 kill 처리
            gsap.killTweensOf(
              $block.find(".textset-subtit, .textset-tit, .textset-desc")
            );
            // 슬라이드 전환 애니메이션
            const $activeSlide = $block
              .find(".swiper-slide")
              .eq(this.activeIndex);
            const $textset = $activeSlide.find(".textset");
            if ($textset.length) {
              // 비활성 슬라이드의 텍스트 인라인 스타일 완전 제거
              $block
                .find(".swiper-slide:not(.swiper-slide-active)")
                .each(function() {
                  const $textElements = $(this).find(
                    ".textset-subtit, .textset-tit, .textset-desc"
                  );
                  $textElements.each(function() {
                    gsap.set(this, {
                      clearProps: "all"
                    });
                    $(this).removeAttr("style");
                    // CSS 초기값으로 재설정
                    gsap.set(this, {
                      y: 50,
                      opacity: 0,
                    });
                  });
                });

              // 새 텍스트 애니메이션 실행
              animateTexts($textset, 0.4);
            }
          },
        },
      });
      // 정지
      $block.find(".pause").click(function() {
        swiper.autoplay.stop();
        $(this).removeClass("active");
        $(this).siblings().addClass("active");
      });
      // 재생
      $block.find(".play").click(function() {
        swiper.autoplay.start();
        $(this).removeClass("active");
        $(this).siblings().addClass("active");
      });
    });
  });
})();
