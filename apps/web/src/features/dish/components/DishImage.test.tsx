import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DishImage } from './DishImage';

describe('DishImage 默认配图', () => {
  it('没有上传图时按菜名加载内置图片', () => {
    render(<DishImage name="番茄炒蛋" />);
    expect(screen.getByRole('img', { name: '番茄炒蛋' })).toHaveAttribute(
      'src',
      '/design/dishes/tomato-eggs.webp',
    );
  });

  it('用户上传图优先于内置图片', () => {
    render(<DishImage name="番茄炒蛋" url="/api/v1/dishes/id/image?v=2" />);
    expect(screen.getByRole('img', { name: '番茄炒蛋' })).toHaveAttribute(
      'src',
      '/api/v1/dishes/id/image?v=2',
    );
  });

  it('没有内置图时继续显示占位', () => {
    render(<DishImage name="未配置图片的菜" />);
    expect(screen.getByText('暂无图片')).toBeInTheDocument();
  });
});
