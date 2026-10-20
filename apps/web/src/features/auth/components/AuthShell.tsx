import type { ReactNode } from 'react';
import '../pages/auth.css';

const DAILY_STANDARDS = [
  { label: '食盐', value: '≤ 5 g' },
  { label: '烹调油', value: '25 ~ 30 g' },
  { label: '食物种类', value: '≥ 12 种' },
];

/** 登录与注册共用的分屏外壳：左侧品牌叙事，右侧表单，窄屏只留表单。 */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="zw-login">
      <section className="zw-login-brand" aria-label="知味校园智慧膳食平台">
        <div className="zw-login-brand-top">
          <span className="zw-login-seal" aria-hidden="true">
            味
          </span>
          <div>
            <strong>知味</strong>
            <small>校园智慧膳食平台</small>
          </div>
        </div>

        <div className="zw-login-brand-main">
          <span className="zw-login-kicker">从食材到餐桌，算清每一餐</span>
          <h1>
            一餐一饭，
            <br />
            知味知营养。
          </h1>
          <p>
            营养核算 · 采购预测 · 决策支持
            <br />
            给校园食堂一张看得懂的每日答卷。
          </p>
        </div>

        <div className="zw-login-standards">
          <span>每日膳食基准</span>
          <dl>
            {DAILY_STANDARDS.map((item) => (
              <div key={item.label}>
                <dt>{item.label}</dt>
                <dd>{item.value}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="zw-login-plate" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
      </section>

      <main className="zw-login-panel">
        <div className="zw-login-form-wrap">
          <div className="zw-login-mobile-brand" aria-hidden="true">
            <span className="zw-login-seal">味</span>
            <strong>知味</strong>
          </div>
          {children}
        </div>
        <footer className="zw-login-foot">知味 · 校园智慧膳食平台</footer>
      </main>
    </div>
  );
}
