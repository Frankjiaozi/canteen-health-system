import { DeleteOutlined, PictureOutlined, UploadOutlined } from '@ant-design/icons';
import { Alert, App, Button, Image, Space, Upload } from 'antd';
import { useEffect, useRef, useState } from 'react';
import type { UploadProps } from 'antd';

export interface DishImageChange {
  file: File | null;
  remove: boolean;
}

export function DishImageUpload({
  currentUrl,
  value,
  onChange,
  disabled = false,
}: {
  currentUrl?: string | null;
  value: DishImageChange;
  onChange: (value: DishImageChange) => void;
  disabled?: boolean;
}) {
  const { message } = App.useApp();
  const [preview, setPreview] = useState<string | null>(null);
  const objectUrl = useRef<string | null>(null);
  useEffect(
    () => () => {
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    },
    [],
  );
  const shown = value.file ? preview : value.remove ? null : currentUrl;
  const beforeUpload: UploadProps['beforeUpload'] = (file) => {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      void message.error('请选择 JPG、PNG 或 WebP 图片');
      return Upload.LIST_IGNORE;
    }
    if (file.size > 5 * 1024 * 1024 || file.size === 0) {
      void message.error('请选择不超过 5MB 的有效图片');
      return Upload.LIST_IGNORE;
    }
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = URL.createObjectURL(file);
    setPreview(objectUrl.current);
    onChange({ file, remove: false });
    return false;
  };
  return (
    <div className="zw-dish-upload">
      <Upload.Dragger
        accept="image/jpeg,image/png,image/webp"
        beforeUpload={beforeUpload}
        showUploadList={false}
        maxCount={1}
        disabled={disabled}
      >
        <PictureOutlined className="zw-upload-icon" />
        <h3>{shown ? '更换菜品图片' : '上传菜品图片'}</h3>
        <p>点击选择或拖拽图片到这里</p>
        <small>JPG、PNG、WebP · 最大 5MB</small>
        <span className="zw-upload-action">
          <UploadOutlined /> 选择图片
        </span>
      </Upload.Dragger>
      <div className="zw-upload-preview-title">
        <h3>图片预览</h3>
        {shown && (
          <Button
            danger
            type="text"
            disabled={disabled}
            icon={<DeleteOutlined />}
            onClick={() => onChange({ file: null, remove: !!currentUrl })}
          >
            移除图片
          </Button>
        )}
      </div>
      {shown ? (
        <Image className="zw-upload-preview" src={shown} alt="待保存的菜品图片" />
      ) : (
        <div className="zw-upload-empty">
          <PictureOutlined />
          <span>上传后在这里预览</span>
        </div>
      )}
      <Space orientation="vertical" size={12}>
        <p className="zw-upload-hint">保存后用于菜品卡片、菜单和助手中的菜品展示。</p>
        {(value.file || value.remove) && (
          <Alert
            type="info"
            showIcon
            title={value.remove ? '保存后将移除原图片' : '图片已选好，保存后生效'}
          />
        )}
      </Space>
    </div>
  );
}
