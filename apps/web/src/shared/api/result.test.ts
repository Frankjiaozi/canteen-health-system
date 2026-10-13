import { describe, expect, it } from 'vitest';
import { ApiError } from './errors';
import { unwrap } from './result';

function fakeResponse(status: number): Response {
  return { status } as Response;
}

describe('unwrap', () => {
  it('成功时直接返回数据', () => {
    const value = unwrap({ data: { username: 'recorder' }, response: fakeResponse(200) });

    expect(value).toEqual({ username: 'recorder' });
  });

  it('失败时抛出带业务错误码的 ApiError', () => {
    expect(() =>
      unwrap({
        error: { code: 'unauthorized', message: '用户名或密码不正确', details: null },
        response: fakeResponse(401),
      }),
    ).toThrowError(ApiError);

    try {
      unwrap({
        error: { code: 'unauthorized', message: '用户名或密码不正确', details: null },
        response: fakeResponse(401),
      });
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      const apiError = error as ApiError;
      expect(apiError.status).toBe(401);
      expect(apiError.code).toBe('unauthorized');
      expect(apiError.message).toBe('用户名或密码不正确');
      expect(apiError.isUnauthorized).toBe(true);
    }
  });

  it('后端返回非标准错误体时给出可读的兜底文案', () => {
    try {
      unwrap({ error: '<html>502 Bad Gateway</html>', response: fakeResponse(502) });
      throw new Error('应当抛出异常');
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).code).toBe('unexpected_response');
      expect((error as ApiError).message).toContain('502');
    }
  });

  it('既没有数据也没有错误时视为异常响应', () => {
    expect(() => unwrap({ response: fakeResponse(204) })).toThrowError(/没有返回数据/);
  });
});
