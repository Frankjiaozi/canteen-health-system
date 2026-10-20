import {
  CameraOutlined,
  LogoutOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { App, Avatar, Button, Drawer, Tag, Upload } from 'antd';
import type { AuthUser } from '../types';
import { canWriteBusinessData } from '../lib/permissions';
import { useLocalAvatar } from '../hooks/useLocalAvatar';
import './account-profile.css';

export function UserAvatar({ user, size = 40 }: { user: AuthUser; size?: number }) {
  const { avatar } = useLocalAvatar(user.id);
  return (
    <Avatar
      size={size}
      src={avatar || undefined}
      className={`zw-account-avatar role-${user.role.toLowerCase()}`}
    >
      {user.display_name.trim().slice(0, 1) || <UserOutlined />}
    </Avatar>
  );
}

export function AccountProfile({
  user,
  open,
  onClose,
  onLogout,
  loggingOut,
}: {
  user: AuthUser;
  open: boolean;
  onClose: () => void;
  onLogout: () => void;
  loggingOut: boolean;
}) {
  const { message } = App.useApp();
  const { avatar, saveAvatar } = useLocalAvatar(user.id);
  const writable = canWriteBusinessData(user);
  const chooseAvatar = async (file: File) => {
    if (
      !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) ||
      file.size > 2 * 1024 * 1024
    ) {
      void message.error('请选择不超过 2 MB 的 JPG、PNG 或 WebP 图片');
      return;
    }
    try {
      const value = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(new Error('图片读取失败'));
        reader.readAsDataURL(file);
      });
      await new Promise<void>((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve();
        img.onerror = () => reject(new Error('图片无法识别，请重新选择'));
        img.src = value;
      });
      saveAvatar(value);
      void message.success('头像已保存在此浏览器');
    } catch {
      void message.error('头像保存失败，请换一张较小的图片重试');
    }
  };
  return (
    <Drawer title="我的账号" open={open} onClose={onClose} size={380} className="zw-account-drawer">
      <div className="zw-account-profile">
        <UserAvatar user={user} size={76} />
        <h2>{user.display_name}</h2>
        <span>@{user.username}</span>
        <Tag icon={<SafetyCertificateOutlined />}>{user.role_label}</Tag>
      </div>
      <div className="zw-avatar-actions">
        <Upload
          accept="image/jpeg,image/png,image/webp"
          showUploadList={false}
          beforeUpload={(file) => {
            void chooseAvatar(file);
            return false;
          }}
        >
          <Button icon={<CameraOutlined />}>更换头像</Button>
        </Upload>
        {avatar && (
          <Button type="text" onClick={() => saveAvatar(null)}>
            恢复默认
          </Button>
        )}
      </div>
      <p className="zw-account-note">
        头像仅保存在此浏览器，按账号独立保存。名称和角色由当前登录账号提供。
      </p>
      <section className="zw-account-permissions">
        <h3>当前账号权限</h3>
        <dl>
          <div>
            <dt>膳食看板、菜品与记录</dt>
            <dd>可查看</dd>
          </div>
          <div>
            <dt>食材、配方与每日采集</dt>
            <dd>{writable ? '可维护' : '只读'}</dd>
          </div>
          <div>
            <dt>菜单生成与发布</dt>
            <dd>{writable ? '可操作' : '只读'}</dd>
          </div>
          <div>
            <dt>膳食助手</dt>
            <dd>{writable ? '规划与查询' : '查询与分析'}</dd>
          </div>
        </dl>
        <p>
          {writable
            ? '可根据现有权限维护食堂数据，发布前仍需确认。'
            : '可查看膳食数据与核算结果，修改和发布操作由录入员或食堂管理员完成。'}
        </p>
      </section>
      <Button
        aria-label="退出登录"
        block
        icon={<LogoutOutlined />}
        onClick={onLogout}
        loading={loggingOut}
      >
        退出登录
      </Button>
    </Drawer>
  );
}
