import { useCurrentUser } from '@/features/auth/hooks/useAuth';
import { canWriteBusinessData } from '@/features/auth/lib/permissions';
import { ArrowRightOutlined, MessageOutlined, CalendarOutlined } from '@ant-design/icons';
import { Button, Carousel, Segmented, Skeleton, Tag, Input } from 'antd';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { DishImage } from '@/features/dish/components/DishImage';
import { SoftCard } from '@/shared/components/SoftCard';
import { useMenuOverview } from '../hooks/useDashboard';
import '@/features/dish/dish.css';
import './menu-samples.css';

export function DashboardMenuPreview() {
  const navigate = useNavigate();
  const { data: user } = useCurrentUser();
  const canWrite = canWriteBusinessData(user);
  const { data, isPending, isError } = useMenuOverview();
  const [question, setQuestion] = useState('');
  const [mealType, setMealType] = useState('LUNCH');
  const tomorrow = data?.days.find((day) => day.date === data.tomorrow);
  const meal = tomorrow?.meals.find((item) => item.meal_type === mealType);
  const slides = [];
  for (let i = 0; i < (meal?.dishes.length ?? 0); i += 3) slides.push(meal!.dishes.slice(i, i + 3));
  return (
    <div className="zw-dashboard-bottom">
      <SoftCard className="zw-menu-preview">
        <header className="zw-dashboard-section-head">
          <div>
            <h2>明日菜单</h2>
            <span>{data?.tomorrow ?? '待安排'}</span>
          </div>
          <Link to="/admin/menu-plan">
            查看菜单 <ArrowRightOutlined />
          </Link>
        </header>
        <Segmented
          value={mealType}
          onChange={setMealType}
          options={[
            { value: 'BREAKFAST', label: '早餐' },
            { value: 'LUNCH', label: '午餐' },
            { value: 'DINNER', label: '晚餐' },
          ]}
        />
        {isPending ? (
          <Skeleton active />
        ) : slides.length ? (
          <Carousel
            key={mealType}
            arrows
            infinite={false}
            autoplay={false}
            dots={slides.length > 1}
          >
            {slides.map((group, index) => (
              <div key={index}>
                <div className="zw-preview-dishes">
                  {group.map((dish) => (
                    <div className="zw-preview-dish" key={dish.dish_id}>
                      <DishImage url={dish.image_url} name={dish.name} />
                      <h3>{dish.name}</h3>
                      <Tag className="zw-tag-sage">{dish.category_label}</Tag>
                      <span>{dish.cooking_method_label}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </Carousel>
        ) : !isError && import.meta.env.VITE_DEMO_MODE === 'true' ? (
          <div className="zw-menu-samples">
            <div className="zw-sample-grid">
              {[
                { name: '番茄炒蛋', tags: ['家常菜', '蛋类'], position: '0%' },
                { name: '清蒸鱼', tags: ['鱼类', '清蒸'], position: '50%' },
                { name: '香菇青菜', tags: ['时令蔬菜', '菌菇'], position: '100%' },
              ].map((dish) => (
                <article className="zw-sample-dish" key={dish.name}>
                  <div
                    className="zw-sample-photo"
                    role="img"
                    aria-label={`${dish.name}示例图片`}
                    style={{ backgroundPosition: `${dish.position} center` }}
                  />
                  <div className="zw-sample-copy">
                    <h3>{dish.name}</h3>
                    <div>
                      {dish.tags.map((tag) => (
                        <span key={tag}>{tag}</span>
                      ))}
                    </div>
                  </div>
                </article>
              ))}
            </div>
            <footer>
              <span>示例菜品 · AI 图片，尚未安排为菜单</span>
              <Link to="/admin/menu-plan">
                {canWrite ? '安排这一餐' : '查看菜单'} <ArrowRightOutlined />
              </Link>
            </footer>
          </div>
        ) : (
          <div className="zw-preview-empty">
            <CalendarOutlined />
            <p>{isError ? '菜单暂时未能读取' : '这一餐还没有安排'}</p>
            <Button onClick={() => void navigate('/admin/menu-plan')}>前往菜单与采购</Button>
          </div>
        )}
      </SoftCard>
      <SoftCard className="zw-dashboard-assistant">
        <svg className="zw-reference-assistant-art" viewBox="1400 655 180 95" aria-hidden="true">
          <image href="/design/ink-reference.png" width="1586" height="992" />
        </svg>
        <span className="zw-assistant-glyph" aria-hidden="true">
          <MessageOutlined />
        </span>
        <h2>膳食助手</h2>
        <p>
          从真实记录出发，规划菜单、核对营养与采购。
          <br />
          每一次调整，都有据可查。
        </p>
        <div className="zw-assistant-suggestions">
          <Button size="small" onClick={() => setQuestion('如何降低菜品含盐量？')}>
            如何降低菜品含盐量？
          </Button>
          <Button size="small" onClick={() => setQuestion('推荐几道低盐家常菜')}>
            推荐几道低盐家常菜
          </Button>
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void navigate(
              `/admin/agent${question.trim() ? `?prompt=${encodeURIComponent(question.trim())}` : ''}`,
            );
          }}
        >
          <Input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={canWrite ? '告诉知味，你想怎样安排下一餐' : '询问膳食数据与营养核算结果'}
            aria-label="向膳食助手提问"
            suffix={
              <Button
                htmlType="submit"
                type="primary"
                shape="circle"
                size="small"
                icon={<ArrowRightOutlined />}
                aria-label="打开膳食助手"
              />
            }
          />
        </form>
        <div className="zw-reference-actions">
          <h3>日常安排</h3>
          <Link to="/admin/menu-plan">
            检查明日菜单 <ArrowRightOutlined />
          </Link>
          <Link to="/admin/collection">
            {canWrite ? '记录今日供餐' : '查看供餐记录'} <ArrowRightOutlined />
          </Link>
        </div>
      </SoftCard>
    </div>
  );
}
