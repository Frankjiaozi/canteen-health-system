import { DownloadOutlined, InboxOutlined } from '@ant-design/icons';
import { Alert, Button, Drawer, Space, Table, Typography, Upload } from 'antd';
import type { TableProps } from 'antd';
import { useState } from 'react';
import { useImportDishes } from '../hooks/useDishes';
import type { ImportIssue, ImportReport } from '../types';

interface ImportDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function ImportDrawer({ open, onClose }: ImportDrawerProps) {
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const importMutation = useImportDishes();

  const reset = () => {
    setFile(null);
    setReport(null);
  };

  const runValidation = async () => {
    if (!file) return;
    setReport(await importMutation.mutateAsync({ file, dryRun: true }));
  };

  const runImport = async () => {
    if (!file) return;
    setReport(await importMutation.mutateAsync({ file, dryRun: false }));
  };

  const errorCount = report?.issues.filter((item) => item.severity === 'error').length ?? 0;

  return (
    <Drawer
      title="批量导入菜品与配方"
      open={open}
      size="large"
      onClose={() => {
        reset();
        onClose();
      }}
      destroyOnHidden
      footer={
        <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button
            icon={<DownloadOutlined />}
            onClick={() => window.open('/api/v1/import/template', '_blank', 'noopener')}
          >
            下载模板
          </Button>
          <Button
            loading={importMutation.isPending}
            disabled={!file}
            onClick={() => void runValidation()}
          >
            校验
          </Button>
          <Button
            type="primary"
            loading={importMutation.isPending}
            disabled={!file || !report || !report.ok || report.dry_run === false}
            onClick={() => void runImport()}
          >
            确认导入
          </Button>
        </Space>
      }
    >
      <Upload.Dragger
        accept=".xlsx"
        maxCount={1}
        beforeUpload={(selected) => {
          setFile(selected);
          setReport(null);
          // 返回 false 阻断 antd 自己的上传：文件由我们在「校验 / 确认导入」时提交
          return false;
        }}
        onRemove={() => reset()}
        fileList={file ? [{ uid: '1', name: file.name, status: 'done' } as never] : []}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">点击或拖拽 .xlsx 文件到这里</p>
        <p className="ant-upload-hint">
          先下载模板，按里面的四个 sheet 填写。名称已存在的按更新处理，菜品配方会被整体替换。
        </p>
      </Upload.Dragger>

      <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>
        先点「校验」看逐行报告；报告里有错误时一行都不会写库，改完再点「确认导入」。
      </Typography.Paragraph>

      {report ? (
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Alert
            type={report.ok ? 'success' : 'error'}
            showIcon
            message={
              report.dry_run
                ? report.ok
                  ? '校验通过，可以确认导入'
                  : `校验发现 ${errorCount} 处错误，修正后重新上传`
                : '导入完成'
            }
          />

          <Table
            rowKey="sheet"
            size="small"
            pagination={false}
            dataSource={report.counts}
            columns={[
              { title: 'Sheet', dataIndex: 'sheet' },
              { title: '新增', dataIndex: 'created', align: 'right', width: 90 },
              { title: '更新', dataIndex: 'updated', align: 'right', width: 90 },
            ]}
          />

          {report.issues.length > 0 ? (
            <Table<ImportIssue>
              rowKey={(row) => `${row.sheet}-${row.row ?? 0}-${row.message}`}
              size="small"
              dataSource={report.issues}
              pagination={{ pageSize: 10, hideOnSinglePage: true }}
              columns={issueColumns}
            />
          ) : (
            <Alert type="success" showIcon message="没有发现任何问题" />
          )}

          {report.recomputed_rows > 0 ? (
            <Typography.Text type="secondary">
              已同步重算 {report.recomputed_rows} 条营养结果。
            </Typography.Text>
          ) : null}
        </Space>
      ) : null}
    </Drawer>
  );
}

const issueColumns: TableProps<ImportIssue>['columns'] = [
  {
    title: '级别',
    dataIndex: 'severity',
    width: 80,
    render: (severity: string) =>
      severity === 'error' ? <Typography.Text type="danger">错误</Typography.Text> : '提示',
  },
  { title: 'Sheet', dataIndex: 'sheet', width: 90 },
  {
    title: '行号',
    dataIndex: 'row',
    width: 80,
    align: 'right',
    render: (row: number | null) => row ?? '—',
  },
  { title: '问题', dataIndex: 'message' },
];
