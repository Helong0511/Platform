/** Cap 配置表单校验（advertiser 校验依赖当前 cap_type） */

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
