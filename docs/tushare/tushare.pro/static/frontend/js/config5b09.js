/**
 * Created by polo on 2018/6/13.
 */

require.config({
  'baseUrl': '/static/vendors/',
  'paths': {
    'jquery': 'jquery/dist/jquery.min',
    'jquery-tui': 'jquery-tui/dist/jquery.min',
    'bootstrap': 'bootstrap/dist/js/bootstrap.min',
    'icheck': 'iCheck/icheck.min',
    'select2': 'select2/dist/js/select2.full.min',
    'validate': 'jquery-validation/dist/jquery.validate',
    'tui-code-snippet': 'tui-code-snippet/dist/tui-code-snippet',
    'markdown-it': 'markdown-it/dist/markdown-it',
    'to-mark': 'to-mark/dist/to-mark',
    'highlight-pack-js': 'highlightjs/highlight.pack',
    'highlight': 'highlight/src/highlight',
    'ace': 'ace-builds/src-noconflict/ace',
    'squire-rte': 'squire-rte/build/squire',
    'tui-viewer': 'tui-editor/dist/tui-editor-Viewer',
    'jstree': 'jstree/jstree.min',
    'mark': 'mark/mark.min',
    'pagination': 'pagination/jquery.twbsPagination.min',
    'custom': '../frontend/js/custom'
  },
  'shim': {
    'bootstrap': {
      'deps': ['jquery']
    },
    'progressbar': {
      'deps': ['jquery', 'bootstrap']
    },
    'icheck': {
      'deps': ['jquery', 'css!\\iCheck/skins/flat/green.css']
    },
    'select2': {
      'deps': ['jquery', 'bootstrap']
    },
    'validate': {
      'deps': ['jquery']
    },
    'tui-viewer': {
      'deps': ['css!\\../../../static/common/css/md.css']
    },
    'jstree': {
      'deps': ['jquery']
    },
    'pagination': {
      'deps': ['jquery']
    },
    'custom': {
      'deps': ['jquery', 'bootstrap', 'validate']
    }
  },
  'map': {
    '*': {
      'css': ['/static/vendors/require-css/css.js']
    }
  }
});
