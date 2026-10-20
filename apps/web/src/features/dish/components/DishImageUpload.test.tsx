import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { beforeEach, expect, it, vi } from 'vitest';
import { DishImageUpload } from './DishImageUpload';

beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  URL.createObjectURL = vi.fn(() => 'blob:test-dish');
  URL.revokeObjectURL = vi.fn();
});

it('默认为空；选择图片后交给表单保存，不自动提交服务器', async () => {
  const onChange = vi.fn();
  const { container } = render(
    <App>
      <DishImageUpload value={{ file: null, remove: false }} onChange={onChange} />
    </App>,
  );
  expect(screen.getByText('上传后在这里预览')).toBeInTheDocument();
  expect(container.querySelector('img')).toBeNull();
  const file = new File(['image'], 'dish.png', { type: 'image/png' });
  fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [file] } });
  await waitFor(() => expect(onChange).toHaveBeenCalledWith({ file, remove: false }));
});

it('不接受 SVG 或超过大小限制的文件', async () => {
  const onChange = vi.fn();
  const { container } = render(
    <App>
      <DishImageUpload value={{ file: null, remove: false }} onChange={onChange} />
    </App>,
  );
  fireEvent.change(container.querySelector('input[type="file"]')!, {
    target: { files: [new File(['<svg/>'], 'dish.svg', { type: 'image/svg+xml' })] },
  });
  await screen.findByText('请选择 JPG、PNG 或 WebP 图片');
  const large = new File(['x'], 'large.png', { type: 'image/png' });
  Object.defineProperty(large, 'size', { value: 5 * 1024 * 1024 + 1 });
  fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [large] } });
  await screen.findByText('请选择不超过 5MB 的有效图片');
  expect(onChange).not.toHaveBeenCalled();
});

it('已有图片可以移除，保存前只标记删除', () => {
  const onChange = vi.fn();
  render(
    <App>
      <DishImageUpload
        currentUrl="/api/v1/dishes/example/image?v=1"
        value={{ file: null, remove: false }}
        onChange={onChange}
      />
    </App>,
  );
  fireEvent.click(screen.getByRole('button', { name: /移除图片/ }));
  expect(onChange).toHaveBeenCalledWith({ file: null, remove: true });
});
