/**
 * DOM 修复工具
 * 修复表单元素可访问性问题和浏览器兼容性问题
 */
import router from '../router';

/**
 * 修复表单元素可访问性问题
 */
export const fixSelectAccessibility = () => {
  const fixSelectInputs = () => {
    const selectInputs = document.querySelectorAll('.el-select .el-select__input, .el-select .el-input__inner, .el-select .el-input__wrapper input');
    selectInputs.forEach((input) => {
      if (!input.getAttribute('title') && !input.getAttribute('placeholder')) {
        const selectEl = input.closest('.el-select');
        if (selectEl) {
          let placeholder = selectEl.getAttribute('placeholder') ||
            selectEl.getAttribute('data-placeholder') ||
            '请选择';

          input.setAttribute('title', placeholder);
          if (input.tagName === 'INPUT' && !input.getAttribute('placeholder')) {
            input.setAttribute('placeholder', placeholder);
          }
          if (!input.getAttribute('aria-label')) {
            input.setAttribute('aria-label', placeholder);
          }
        } else {
          input.setAttribute('title', '请选择');
          if (!input.getAttribute('aria-label')) {
            input.setAttribute('aria-label', '请选择');
          }
        }
      } else if (!input.getAttribute('aria-label')) {
        const label = input.getAttribute('title') || input.getAttribute('placeholder') || '请选择';
        input.setAttribute('aria-label', label);
      }
    });
  };

  const fixDatePickerInputs = () => {
    const datePickerInputs = document.querySelectorAll('.el-date-picker .el-input__inner, .el-date-editor .el-input__inner, .el-date-editor input');
    datePickerInputs.forEach((input) => {
      if (!input.getAttribute('title') && !input.getAttribute('placeholder')) {
        const datePickerEl = input.closest('.el-date-picker, .el-date-editor');
        if (datePickerEl) {
          let placeholder = datePickerEl.getAttribute('placeholder') ||
            datePickerEl.getAttribute('start-placeholder') ||
            datePickerEl.getAttribute('end-placeholder') ||
            '请选择日期';

          input.setAttribute('title', placeholder);
          if (input.tagName === 'INPUT' && !input.getAttribute('placeholder')) {
            input.setAttribute('placeholder', placeholder);
          }
          if (!input.getAttribute('aria-label')) {
            input.setAttribute('aria-label', placeholder);
          }
        } else {
          input.setAttribute('title', '请选择日期');
          if (!input.getAttribute('aria-label')) {
            input.setAttribute('aria-label', '请选择日期');
          }
        }
      } else if (!input.getAttribute('aria-label')) {
        const label = input.getAttribute('title') || input.getAttribute('placeholder') || '请选择日期';
        input.setAttribute('aria-label', label);
      }
    });
  };

  const fixOtherFormInputs = () => {
    const otherInputs = document.querySelectorAll('.el-autocomplete input, .el-cascader input, .el-time-picker input');
    otherInputs.forEach((input) => {
      if (!input.getAttribute('title') && !input.getAttribute('placeholder') && !input.getAttribute('aria-label')) {
        const parentEl = input.closest('.el-autocomplete, .el-cascader, .el-time-picker');
        let placeholder = '请输入';

        if (parentEl) {
          placeholder = parentEl.getAttribute('placeholder') ||
            parentEl.getAttribute('data-placeholder') ||
            placeholder;
        }

        input.setAttribute('title', placeholder);
        if (input.tagName === 'INPUT' && !input.getAttribute('placeholder')) {
          input.setAttribute('placeholder', placeholder);
        }
        input.setAttribute('aria-label', placeholder);
      }
    });
  };

  const fixAllInputs = () => {
    fixSelectInputs();
    fixDatePickerInputs();
    fixOtherFormInputs();
  };

  // 立即执行一次修复
  setTimeout(fixAllInputs, 100);

  // 在路由变化后也执行修复
  if (router) {
    router.afterEach(() => {
      setTimeout(fixAllInputs, 200);
    });
  }

  // 使用 MutationObserver 监听 DOM 变化
  const observer = new MutationObserver(() => {
    fixAllInputs();
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true
  });
};

/**
 * 修复 -moz-appearance 兼容性问题
 */
export const fixMozAppearance = () => {
  // 方法1：通过内联样式修复
  const elementsWithMozAppearance = document.querySelectorAll('[style*="-moz-appearance"]');
  elementsWithMozAppearance.forEach((el) => {
    const style = el.getAttribute('style') || '';
    if (style.includes('-moz-appearance') && !style.includes('appearance:')) {
      const match = style.match(/-moz-appearance:\s*([^;]+)/);
      if (match) {
        const value = match[1].trim();
        el.style.appearance = value;
      }
    }
  });

  // 方法2：通过计算样式修复
  const allInputs = document.querySelectorAll('input, .el-input__inner, .el-input_inner, .el-input__wrapper');
  allInputs.forEach((el) => {
    const computedStyle = window.getComputedStyle(el);
    const mozAppearance = computedStyle.getPropertyValue('-moz-appearance');
    const appearance = computedStyle.getPropertyValue('appearance');

    if (mozAppearance && mozAppearance !== 'none' && (!appearance || appearance === 'none' || appearance === 'auto')) {
      if (mozAppearance.trim() === 'textfield') {
        el.style.appearance = 'textfield';
      } else {
        el.style.appearance = mozAppearance;
      }
    }
  });

  // 方法3：专门修复 Element Plus 分页组件中的输入框
  const paginationInputs = document.querySelectorAll('.el-pagination input, .el-pagination .el-input__inner, .el-pagination .el-input_inner');
  paginationInputs.forEach((el) => {
    const computedStyle = window.getComputedStyle(el);
    const mozAppearance = computedStyle.getPropertyValue('-moz-appearance');
    const appearance = computedStyle.getPropertyValue('appearance');

    if (mozAppearance && mozAppearance.trim() === 'textfield' && (!appearance || appearance === 'none' || appearance === 'auto')) {
      el.style.appearance = 'textfield';
    }
  });
};

/**
 * 修复 mask 相关属性的兼容性问题
 */
export const fixMaskProperties = () => {
  const fixMaskImage = (el) => {
    const computedStyle = window.getComputedStyle(el);
    const maskImage = computedStyle.getPropertyValue('mask-image');
    const webkitMaskImage = computedStyle.getPropertyValue('-webkit-mask-image');

    if (maskImage && maskImage !== 'none' && !webkitMaskImage) {
      el.style.setProperty('-webkit-mask-image', maskImage, 'important');
    }

    const style = el.getAttribute('style') || '';
    if (style.includes('mask-image:') && !style.includes('-webkit-mask-image:')) {
      const match = style.match(/mask-image:\s*([^;]+)/);
      if (match) {
        const value = match[1].trim();
        el.style.setProperty('-webkit-mask-image', value, 'important');
      }
    }
  };

  const fixMaskPosition = (el) => {
    const computedStyle = window.getComputedStyle(el);
    const maskPosition = computedStyle.getPropertyValue('mask-position');
    const webkitMaskPosition = computedStyle.getPropertyValue('-webkit-mask-position');

    if (maskPosition && maskPosition !== 'initial' && !webkitMaskPosition) {
      el.style.setProperty('-webkit-mask-position', maskPosition, 'important');
    }

    const style = el.getAttribute('style') || '';
    if (style.includes('mask-position:') && !style.includes('-webkit-mask-position:')) {
      const match = style.match(/mask-position:\s*([^;]+)/);
      if (match) {
        const value = match[1].trim();
        el.style.setProperty('-webkit-mask-position', value, 'important');
      }
    }
  };

  const fixMaskRepeat = (el) => {
    const computedStyle = window.getComputedStyle(el);
    const maskRepeat = computedStyle.getPropertyValue('mask-repeat');
    const webkitMaskRepeat = computedStyle.getPropertyValue('-webkit-mask-repeat');

    if (maskRepeat && maskRepeat !== 'initial' && !webkitMaskRepeat) {
      el.style.setProperty('-webkit-mask-repeat', maskRepeat, 'important');
    }

    const style = el.getAttribute('style') || '';
    if (style.includes('mask-repeat:') && !style.includes('-webkit-mask-repeat:')) {
      const match = style.match(/mask-repeat:\s*([^;]+)/);
      if (match) {
        const value = match[1].trim();
        el.style.setProperty('-webkit-mask-repeat', value, 'important');
      }
    }
  };

  // 检查内联样式
  const elementsWithMaskInStyle = document.querySelectorAll('[style*="mask-image"], [style*="mask-position"], [style*="mask-repeat"]');
  elementsWithMaskInStyle.forEach((el) => {
    fixMaskImage(el);
    fixMaskPosition(el);
    fixMaskRepeat(el);
  });

  // 检查计算样式
  const potentialMaskElements = document.querySelectorAll('[class*="mask"], [class*="close-button"], [class*="button"], .el-select-dropdown__item');
  potentialMaskElements.forEach((el) => {
    const computedStyle = window.getComputedStyle(el);
    const hasMaskImage = computedStyle.getPropertyValue('mask-image') !== 'none';
    const hasMaskPosition = computedStyle.getPropertyValue('mask-position') !== 'initial' && computedStyle.getPropertyValue('mask-position') !== '';
    const hasMaskRepeat = computedStyle.getPropertyValue('mask-repeat') !== 'initial' && computedStyle.getPropertyValue('mask-repeat') !== '';

    if (hasMaskImage) {
      fixMaskImage(el);
    }
    if (hasMaskPosition) {
      fixMaskPosition(el);
    }
    if (hasMaskRepeat) {
      fixMaskRepeat(el);
    }
  });
};

/**
 * 初始化所有 DOM 修复
 */
export const initDomFixes = () => {
  fixSelectAccessibility();
  fixMozAppearance();
  fixMaskProperties();

  // 使用 MutationObserver 监听 DOM 变化
  const observer = new MutationObserver(() => {
    fixMozAppearance();
    fixMaskProperties();
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['style', 'class']
  });
};

