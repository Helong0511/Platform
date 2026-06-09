/**
 * Cap 配置表单校验规则
 * @file utils/capFormRules.js
 *
 * advertiser 字段校验依赖当前 cap_type，advertiser_offer 类型时必填。
 * @param {Function} getFormData - 获取当前表单数据的函数
 * @returns {Object} Element Plus 表单 rules 对象
 */
export function createCapFormRules(getFormData) {
  return {
    cap_type: [{ required: true, message: '请选择Cap类型', trigger: 'change' }],
    offer_id: [{ required: true, message: '请选择Offer', trigger: 'change' }],
    advertiser_id: [
      {
        trigger: 'change',
        validator: (_rule, value, callback) => {
          if (getFormData().cap_type === 'advertiser_offer' && !value) {
            callback(new Error('advertiser_offer类型必须选择广告主'));
          } else {
            callback();
          }
        },
      },
    ],
  };
}
