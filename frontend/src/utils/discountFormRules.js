/** 扣量配置表单校验 */

export function createDiscountFormRules(getFormData) {
  return {
    discount_type: [{ required: true, message: '请选择扣量类型', trigger: 'change' }],
    publisher_id: [{ required: true, message: '请选择渠道', trigger: 'change' }],
    offer_id: [
      {
        trigger: 'change',
        validator: (_rule, value, callback) => {
          if (getFormData().discount_type === 'offer' && !value) {
            callback(new Error('offer类型必须选择Offer'));
          } else {
            callback();
          }
        },
      },
    ],
    discount_ratio: [
      { required: true, message: '请输入扣量比例', trigger: 'blur' },
      {
        type: 'number',
        min: 0,
        max: 100,
        message: '扣量比例必须在0-100之间',
        trigger: 'blur',
      },
    ],
  };
}
