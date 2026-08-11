from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_backup_script_is_mysql_and_restore_verified():
    script = (ROOT / "scripts" / "backup_db.sh").read_text(encoding="utf-8")
    assert "mysqldump" in script
    assert "--single-transaction" in script
    assert "--verify-restore" in script
    assert "restore_verified=" in script
    assert "sqlite" not in script.lower()


def test_deploy_script_enforces_backup_migration_health_and_login_order():
    script = (ROOT / "scripts" / "deploy_prod.sh").read_text(encoding="utf-8")
    checkpoints = [
        'step "1/9 Backup and restore verification"',
        'step "5/9 Run explicit MySQL migration"',
        'step "7/9 Health checks"',
        'step "8/9 Login and database preservation"',
    ]
    positions = [script.index(checkpoint) for checkpoint in checkpoints]
    assert positions == sorted(positions)
    assert "DEPLOY_ADMIN_USERNAME" in script
    assert "DEPLOY_ADMIN_PASSWORD" in script
    assert "systemctl" not in script
    assert "sqlite" not in script.lower()


def test_application_startup_does_not_alter_existing_schema():
    main_source = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert "ALTER TABLE" not in main_source
    assert "_migrate_test_case_columns" not in main_source


def test_production_uses_one_explicit_migration_command():
    production_entrypoint = (ROOT / "scripts" / "migrate_prod.sh").read_text(encoding="utf-8")
    migration = (ROOT / "backend" / "scripts" / "migrate.py").read_text(encoding="utf-8")
    initializer = (ROOT / "backend" / "scripts" / "init_db.py").read_text(encoding="utf-8")

    assert "scripts/migrate.py" in production_entrypoint
    assert "scripts/init_db.py" not in production_entrypoint
    assert "migrate_mysql_schema" in migration
    assert "migrate_phase_a" in migration
    assert "forbidden in production" in initializer
