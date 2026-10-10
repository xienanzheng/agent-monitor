# Building and publishing

From a development checkout:

```sh
npm run build:dashboard
npm test
npm run release:build
```

The release builder requires a fresh destination and exports an explicit subset. It produces a source ZIP, an npm tarball, SHA256 checksums and its packing manifest under `dist/agent-monitor-0.1.0/`. The source includes built assets and tests. Runtime logs, real data, local results, machine settings and historical screenshots are excluded. Review the exported files and license before publishing.

To test the actual artifact without registry publication:

```sh
npx --yes --package ./dist/agent-monitor-0.1.0/xienanzheng-agent-monitor-0.1.0.tgz agent-monitor init ./downloaded-monitor
cd downloaded-monitor
npm run setup
npm run doctor
```

`npm install` has no lifecycle scripts. `init` writes only the new project folder. `setup` installs Python dependencies. Hooks and model downloads are separate opt-in commands.

Publish the tested tarball after authenticating with an npm account that owns the package scope:

```sh
npm login
npm publish ./dist/agent-monitor-0.1.0/xienanzheng-agent-monitor-0.1.0.tgz --access public
```

Registry publication is distinct from creating a GitHub source repository. Keep the original private development repository private if its history includes real traffic. A clean exported snapshot is the basis for the public repository. Future updates should use that public repository and repeat artifact tests, rather than copying private history into it.
