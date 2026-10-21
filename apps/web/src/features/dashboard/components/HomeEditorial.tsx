import { ArrowRightOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Skeleton } from 'antd';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMenuOverview } from '../hooks/useDashboard';
import './home-editorial.css';

export function HomeEditorial() {
  const { data, isPending, isError, refetch } = useMenuOverview();
  const [mealType, setMealType] = useState('LUNCH');
  const today = data?.days.find((day) => day.date === data.today);
  const meal = today?.meals.find((item) => item.meal_type === mealType);
  return (
    <main className="zw-editorial">
      <section className="zw-home-intro">
        <div className="zw-home-intro-copy">
          <p className="zw-home-date">
            {data?.today
              ? new Date(`${data.today}T12:00:00`).toLocaleDateString('zh-CN', {
                  month: 'long',
                  day: 'numeric',
                  weekday: 'long',
                })
              : '今日膳食'}
            <span>
              {import.meta.env.VITE_DEMO_MODE === 'true'
                ? '独立演示 · 合成数据'
                : '一餐一饭，皆有心意'}
            </span>
          </p>
          <h1>
            知食之味，
            <br />
            养日常之美。
          </h1>
          <p className="zw-home-description">
            把时令与营养，写进每一天的菜单。
            <br />
            从一餐的用心，照顾每一个日常。
          </p>
          <Link className="zw-home-primary" to="/admin/agent">
            与知味一起，安排下一餐 <ArrowRightOutlined />
          </Link>
        </div>
        <div className="zw-home-art" aria-hidden="true">
          <svg viewBox="0 0 640 410" fill="none">
            <defs>
              <radialGradient id="tea-wash">
                <stop stopColor="#b8c4a5" stopOpacity=".48" />
                <stop offset="1" stopColor="#dce1cd" stopOpacity="0" />
              </radialGradient>
              <linearGradient
                id="ceramic"
                x1="200"
                y1="150"
                x2="400"
                y2="350"
                gradientUnits="userSpaceOnUse"
              >
                <stop stopColor="#fbfaf0" />
                <stop offset=".55" stopColor="#e4e9d7" />
                <stop offset="1" stopColor="#a3b298" />
              </linearGradient>
              <filter id="soft-shadow">
                <feGaussianBlur stdDeviation="9" />
              </filter>
            </defs>
            <ellipse cx="340" cy="230" rx="290" ry="190" fill="url(#tea-wash)" />
            <ellipse
              cx="320"
              cy="347"
              rx="156"
              ry="13"
              fill="#53634b"
              opacity=".13"
              filter="url(#soft-shadow)"
            />
            <path
              d="M158 208 Q173 331 303 342 Q429 337 448 208"
              fill="url(#ceramic)"
              stroke="#9cac91"
              strokeOpacity=".4"
            />
            <ellipse
              cx="303"
              cy="207"
              rx="145"
              ry="49"
              fill="#f8f7eb"
              stroke="#b3bda3"
              strokeWidth="2"
            />
            <ellipse cx="303" cy="208" rx="126" ry="34" fill="#d9dfc9" />
            <path
              d="M195 208 Q238 172 270 202 Q302 169 327 199 Q364 176 403 211 Q364 240 304 236 Q233 235 195 208"
              fill="#eef0de"
            />
            <g stroke="#657e58" strokeWidth="2">
              <path d="M313 222 Q353 163 391 154" />
              <path d="M342 187 Q324 155 345 149 Q369 165 342 187" fill="#81956c" />
              <path d="M359 171 Q373 137 392 142 Q395 163 359 171" fill="#97a77f" />
              <path d="M370 163 Q399 165 406 181 Q378 194 370 163" fill="#6f8762" />
            </g>
            <path
              d="M212 273 Q235 300 267 304"
              stroke="#fffef8"
              strokeWidth="4"
              opacity=".65"
              strokeLinecap="round"
            />
            <g stroke="#9b7955" strokeWidth="5" strokeLinecap="round">
              <path d="M397 287 L548 153" />
              <path d="M410 296 L560 164" />
            </g>
            <g stroke="#6c7c5d" strokeWidth="1.3">
              <path d="M525 21 Q469 94 488 162" />
              <path d="M505 50 Q459 40 469 71 Q493 77 505 50" fill="#a7b395" />
              <path d="M492 77 Q522 47 535 68 Q526 91 492 77" fill="#899c79" />
              <path d="M485 103 Q444 83 446 113 Q468 125 485 103" fill="#bac2a8" />
              <path d="M485 126 Q518 97 527 120 Q515 140 485 126" fill="#98aa86" />
            </g>
          </svg>
          <span className="zw-art-poem">食有时 · 味有知</span>
          <span className="zw-art-seal">
            知<br />味
          </span>
        </div>
      </section>
      <section className="zw-home-menu">
        <header>
          <div>
            <span className="zw-section-caption">餐桌上的日常</span>
            <h2>今日好食</h2>
          </div>
          <div className="zw-meal-switch" role="group" aria-label="选择餐次">
            {[
              ['BREAKFAST', '早餐'],
              ['LUNCH', '午餐'],
              ['DINNER', '晚餐'],
            ].map(([value, label]) => (
              <button
                key={value}
                aria-pressed={mealType === value}
                onClick={() => setMealType(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <Link to="/admin/menu-plan">
            完整菜单 <ArrowRightOutlined />
          </Link>
        </header>
        {isPending ? (
          <Skeleton active />
        ) : isError ? (
          <div className="zw-home-empty">
            菜单暂时未能读取。
            <Button type="link" onClick={() => void refetch()}>
              重新加载
            </Button>
          </div>
        ) : meal?.dishes.length ? (
          <div className="zw-home-dishes">
            {meal.dishes.slice(0, 3).map((dish) => (
              <article
                className={`zw-home-dish${dish.image_url ? ' has-photo' : ''}`}
                key={dish.dish_id}
              >
                {dish.image_url && <img src={dish.image_url} alt={dish.name} />}
                <div>
                  <span>
                    {dish.category_label} / {dish.cooking_method_label}
                  </span>
                  <h3>{dish.name}</h3>
                  <Link to="/admin/dishes">
                    {dish.image_url ? (
                      '查看菜品'
                    ) : (
                      <>
                        <PlusOutlined /> 添加菜品照片
                      </>
                    )}
                  </Link>
                </div>
                <span className="zw-dish-watermark" aria-hidden="true">
                  {dish.category_label.slice(0, 1)}
                </span>
              </article>
            ))}
          </div>
        ) : (
          <div className="zw-home-empty">
            <h3>留一页，给今天的好味道。</h3>
            <p>这一餐还没有安排，和膳食助手一起拟一份菜单。</p>
            <Link to="/admin/agent">
              开始安排 <ArrowRightOutlined />
            </Link>
          </div>
        )}
      </section>
      <footer className="zw-home-bottom">
        <div>
          <span className="zw-mini-seal">膳</span>
          <div>
            <h3>下一餐的灵感，从这里开始。</h3>
            <p>规划菜单、核对营养、整理采购，让每一餐都有据可依。</p>
          </div>
        </div>
        <Link to="/admin/agent">
          告诉知味你的想法 <ArrowRightOutlined />
        </Link>
      </footer>
    </main>
  );
}
