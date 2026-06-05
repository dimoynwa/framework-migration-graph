#!/usr/bin/env node
'use strict';

const fs = require('fs');

const inputPath = process.argv[2];
const outputPath = process.argv[3];
if (!inputPath || !outputPath) {
  console.error('Usage: node ua-arch-analyze.js <input.json> <output.json>');
  process.exit(1);
}

const { fileNodes, importEdges, allEdges } = JSON.parse(fs.readFileSync(inputPath, 'utf8'));

// ---- A. Directory Grouping ----
// Find common path prefix
function getCommonPrefix(paths) {
  if (!paths.length) return '';
  const parts = paths[0].split('/');
  let prefix = [];
  for (let i = 0; i < parts.length - 1; i++) {
    if (paths.every(p => p.split('/')[i] === parts[i])) {
      prefix.push(parts[i]);
    } else break;
  }
  return prefix.join('/');
}

const allPaths = fileNodes.map(n => n.filePath || n.id.replace(/^[^:]+:/, ''));
const commonPrefix = getCommonPrefix(allPaths);

function getGroupKey(filePath) {
  let path = filePath;
  if (commonPrefix && path.startsWith(commonPrefix + '/')) {
    path = path.slice(commonPrefix.length + 1);
  }
  const parts = path.split('/');
  if (parts.length === 1) return 'root';
  return parts[0];
}

const directoryGroups = {};
fileNodes.forEach(n => {
  const fp = n.filePath || n.id.replace(/^[^:]+:/, '');
  const grp = getGroupKey(fp);
  if (!directoryGroups[grp]) directoryGroups[grp] = [];
  directoryGroups[grp].push(n.id);
});

// ---- B. Node Type Grouping ----
const nodeTypeGroups = {};
fileNodes.forEach(n => {
  if (!nodeTypeGroups[n.type]) nodeTypeGroups[n.type] = [];
  nodeTypeGroups[n.type].push(n.id);
});

// ---- C. Import Adjacency / Fan-in / Fan-out ----
const fanIn = {};
const fanOut = {};
fileNodes.forEach(n => { fanIn[n.id] = 0; fanOut[n.id] = 0; });

importEdges.forEach(e => {
  fanOut[e.source] = (fanOut[e.source] || 0) + 1;
  fanIn[e.target] = (fanIn[e.target] || 0) + 1;
});

// ---- D. Cross-Category Dependency Analysis ----
const nodeTypeMap = {};
fileNodes.forEach(n => { nodeTypeMap[n.id] = n.type; });

const crossCategoryMap = {};
allEdges.forEach(e => {
  const fromType = nodeTypeMap[e.source];
  const toType = nodeTypeMap[e.target];
  if (!fromType || !toType) return;
  const key = `${fromType}|${toType}|${e.type}`;
  crossCategoryMap[key] = (crossCategoryMap[key] || 0) + 1;
});
const crossCategoryEdges = Object.entries(crossCategoryMap).map(([key, count]) => {
  const [fromType, toType, edgeType] = key.split('|');
  return { fromType, toType, edgeType, count };
});

// ---- E. Inter-Group Import Frequency ----
const nodeGroupMap = {};
fileNodes.forEach(n => {
  const fp = n.filePath || n.id.replace(/^[^:]+:/, '');
  nodeGroupMap[n.id] = getGroupKey(fp);
});

const interGroupMap = {};
importEdges.forEach(e => {
  const fromGrp = nodeGroupMap[e.source];
  const toGrp = nodeGroupMap[e.target];
  if (!fromGrp || !toGrp || fromGrp === toGrp) return;
  const key = `${fromGrp}|${toGrp}`;
  interGroupMap[key] = (interGroupMap[key] || 0) + 1;
});
const interGroupImports = Object.entries(interGroupMap).map(([key, count]) => {
  const [from, to] = key.split('|');
  return { from, to, count };
}).sort((a, b) => b.count - a.count);

// ---- F. Intra-Group Import Density ----
const groupEdgeCounts = {};
const groupInternalCounts = {};
Object.keys(directoryGroups).forEach(g => {
  groupEdgeCounts[g] = 0;
  groupInternalCounts[g] = 0;
});

importEdges.forEach(e => {
  const fg = nodeGroupMap[e.source];
  const tg = nodeGroupMap[e.target];
  if (fg) groupEdgeCounts[fg] = (groupEdgeCounts[fg] || 0) + 1;
  if (tg) groupEdgeCounts[tg] = (groupEdgeCounts[tg] || 0) + 1;
  if (fg && tg && fg === tg) groupInternalCounts[fg] = (groupInternalCounts[fg] || 0) + 1;
});

const intraGroupDensity = {};
Object.keys(directoryGroups).forEach(g => {
  const total = groupEdgeCounts[g] || 0;
  const internal = groupInternalCounts[g] || 0;
  intraGroupDensity[g] = {
    internalEdges: internal,
    totalEdges: total,
    density: total > 0 ? parseFloat((internal / total).toFixed(3)) : 0
  };
});

// ---- G. Directory Pattern Matching ----
const patternMap = {
  routes: 'api', api: 'api', controllers: 'api', endpoints: 'api', handlers: 'api',
  routers: 'api', blueprints: 'api', serializers: 'api', controller: 'api',
  services: 'service', core: 'service', lib: 'service', domain: 'service', logic: 'service',
  composables: 'service', signals: 'service', mailers: 'service', jobs: 'service', channels: 'service',
  internal: 'service',
  models: 'data', db: 'data', data: 'data', persistence: 'data', repository: 'data',
  entities: 'data', migrations: 'data', entity: 'data', sql: 'data', database: 'data', schema: 'data',
  components: 'ui', views: 'ui', pages: 'ui', ui: 'ui', layouts: 'ui', screens: 'ui',
  middleware: 'middleware', plugins: 'middleware', interceptors: 'middleware', guards: 'middleware',
  utils: 'utility', helpers: 'utility', common: 'utility', shared: 'utility', tools: 'utility',
  pkg: 'utility', templatetags: 'utility',
  config: 'config', constants: 'config', env: 'config', settings: 'config',
  management: 'config', commands: 'config',
  '__tests__': 'test', test: 'test', tests: 'test', spec: 'test', specs: 'test',
  types: 'types', interfaces: 'types', schemas: 'types', contracts: 'types', dtos: 'types',
  hooks: 'hooks',
  store: 'state', state: 'state', reducers: 'state', actions: 'state', slices: 'state',
  assets: 'assets', static: 'assets', public: 'assets',
  bin: 'entry', cmd: 'entry',
  docs: 'documentation', documentation: 'documentation', wiki: 'documentation',
  deploy: 'infrastructure', deployment: 'infrastructure', infra: 'infrastructure',
  infrastructure: 'infrastructure',
  '.github': 'ci-cd', '.gitlab': 'ci-cd', '.circleci': 'ci-cd',
  k8s: 'infrastructure', kubernetes: 'infrastructure', helm: 'infrastructure',
  terraform: 'infrastructure', tf: 'infrastructure', docker: 'infrastructure',
  dto: 'types', request: 'types', response: 'types',
};

const patternMatches = {};
Object.keys(directoryGroups).forEach(g => {
  patternMatches[g] = patternMap[g.toLowerCase()] || 'unknown';
});

// ---- H. Deployment Topology Detection ----
const allFilePaths = fileNodes.map(n => n.filePath || n.id.replace(/^[^:]+:/, ''));
const infraFiles = allFilePaths.filter(p =>
  /Dockerfile/.test(p) || /docker-compose/.test(p) ||
  /\.tf$/.test(p) || /\.tfvars$/.test(p) ||
  /k8s|kubernetes|helm/.test(p) ||
  /\.github\/workflows/.test(p) || /\.gitlab-ci/.test(p) || /Jenkinsfile/.test(p) ||
  /Makefile$/.test(p)
);
const deploymentTopology = {
  hasDockerfile: allFilePaths.some(p => /Dockerfile$/.test(p)),
  hasCompose: allFilePaths.some(p => /docker-compose/.test(p)),
  hasK8s: allFilePaths.some(p => /k8s|kubernetes/.test(p)),
  hasTerraform: allFilePaths.some(p => /\.tf$/.test(p)),
  hasCI: allFilePaths.some(p => /\.github\/workflows|\.gitlab-ci|Jenkinsfile/.test(p)),
  infraFiles
};

// ---- I. Data Pipeline Detection ----
const dataPipeline = {
  schemaFiles: allFilePaths.filter(p => /\.graphql$|\.gql$|\.proto$|schema\.sql/.test(p)),
  migrationFiles: allFilePaths.filter(p => /migrations?\//i.test(p)),
  dataModelFiles: allFilePaths.filter(p => /models?\//i.test(p)),
  apiHandlerFiles: allFilePaths.filter(p => /routes?\/|controllers?\/|endpoints?\//i.test(p))
};

// ---- J. Documentation Coverage ----
const groupsWithDocs = new Set();
fileNodes.filter(n => n.type === 'document').forEach(n => {
  const fp = n.filePath || n.id.replace(/^[^:]+:/, '');
  groupsWithDocs.add(getGroupKey(fp));
});
const allGroups = Object.keys(directoryGroups);
const docCoverage = {
  groupsWithDocs: groupsWithDocs.size,
  totalGroups: allGroups.length,
  coverageRatio: parseFloat((groupsWithDocs.size / allGroups.length).toFixed(2)),
  undocumentedGroups: allGroups.filter(g => !groupsWithDocs.has(g))
};

// ---- K. Dependency Direction ----
const dependencyDirection = interGroupImports
  .filter(({ from, to }) => {
    const reverse = interGroupImports.find(x => x.from === to && x.to === from);
    const reverseCount = reverse ? reverse.count : 0;
    return interGroupImports.find(x => x.from === from && x.to === to).count > reverseCount;
  })
  .map(({ from, to }) => ({ dependent: from, dependsOn: to }));

// ---- File Stats ----
const filesPerGroup = {};
Object.entries(directoryGroups).forEach(([g, ids]) => { filesPerGroup[g] = ids.length; });
const nodeTypeCounts = {};
Object.entries(nodeTypeGroups).forEach(([t, ids]) => { nodeTypeCounts[t] = ids.length; });

const result = {
  scriptCompleted: true,
  directoryGroups,
  nodeTypeGroups,
  crossCategoryEdges,
  interGroupImports,
  intraGroupDensity,
  patternMatches,
  deploymentTopology,
  dataPipeline,
  docCoverage,
  dependencyDirection,
  fileStats: {
    totalFileNodes: fileNodes.length,
    filesPerGroup,
    nodeTypeCounts
  },
  fileFanIn: fanIn,
  fileFanOut: fanOut
};

fs.writeFileSync(outputPath, JSON.stringify(result, null, 2));
console.log('Done. Groups:', Object.keys(directoryGroups).join(', '));
