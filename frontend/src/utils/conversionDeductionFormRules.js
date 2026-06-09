/**
 * 转化扣减配置表单校验规则
 * @file utils/conversionDeductionFormRules.js
 *
 * @param {Function} getForm - 获取当前表单数据的函数
 * @returns {Object} Element Plus 表单 rules 对象
 */
export function createConversionDeductionFormRules(getForm) {
  return {
    level: [{ required: true, message: '请选择配置层级', trigger: 'change' }],
    target_id: [{ required: true, message: '请选择配置对象', trigger: 'change' }],
    volume_deduction_ratio: [
      {
        validator: (_rule, value, callback) => {
          const form = getForm();
          if (form.enable_volume_deduction && (!value || value <= 0)) {
            callback(new Error('启用扣量时，扣量比例必须大于0'));
          } else {
            callback();
          }
        },
        trigger: 'blur',
      },
    ],
    amount_deduction_ratio: [
      {
        validator: (_rule, value, callback) => {
          const form = getForm();
          if (form.enable_amount_deduction && (!value || value <= 0)) {
            callback(new Error('启用扣金额时，扣金额比例必须大于0'));
          } else {
            callback();
          }
        },
        trigger: 'blur',
      },
    ],
  };
}

/**
 * emptyConversionDeductionForm 接口。
 */
export function emptyConversionDeductionForm() {
  return {
    level: 'advertiser',
    target_id: null,
    enable_volume_deduction: false,
    volume_deduction_ratio: 0,
    deduction_strategy: 'random',
    enable_amount_deduction: false,
    amount_deduction_ratio: 0,
    priority: 0,
    is_active: true,
  };
}
