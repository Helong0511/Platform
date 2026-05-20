/** 短链接表单校验规则 */

export const shortLinkFormRules = {
  original_url: [
    { required: true, message: '请输入原始URL', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (!value) {
          callback();
          return;
        }
        try {
          const url = new URL(value);
          if (!url.protocol || !url.hostname) {
            callback(new Error('URL格式无效，必须包含协议和域名'));
          } else {
            callback();
          }
        } catch {
          callback(new Error('URL格式无效'));
        }
      },
      trigger: 'blur',
    },
  ],
  short_code: [
    {
      validator: (_rule, value, callback) => {
        if (!value) {
          callback();
          return;
        }
        if (!/^[a-zA-Z0-9_-]+$/.test(value)) {
          callback(new Error('短链接代码只能包含字母、数字、连字符和下划线'));
        } else if (value.length < 3) {
          callback(new Error('短链接代码至少需要3个字符'));
        } else if (value.length > 20) {
          callback(new Error('短链接代码最多20个字符'));
        } else {
          callback();
        }
      },
      trigger: 'blur',
    },
  ],
};
