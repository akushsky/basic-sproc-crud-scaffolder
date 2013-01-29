#!/usr/bin/python
import os
import argparse
import psycopg2

import plpgsql
import java

import psycopg2
import psycopg2.extras

connection_string = ""

def setConnectionString(conn_string):
    global connection_string
    connection_string = conn_string

def getConnection():
    conn = psycopg2.connect(connection_string)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SET work_mem TO '64MB';")
    cur.close()
    return conn

def closeConnection(c):
    c.close()

def getAssociationsForTable(schema,table):
    conn = getConnection()
    cursor = conn.cursor()

def getFieldsForTable(schema,table):
  conn = getConnection();
  cursor = conn.cursor()
  cursor.execute("""select column_name, data_type, character_maximum_length, column_default, lower(is_nullable),
                           (select column_name in ( select column_name
                                                      from information_schema.key_column_usage kcu,
                                                           information_schema.table_constraints tc
                                                     where tc.table_name = c.table_name
                                                       and tc.table_schema = c.table_schema
                                                       and kcu.constraint_name = tc.constraint_name
                                                       and tc.constraint_type = 'PRIMARY KEY' ) ) as is_primary_part,
                           udt_name
                      from information_schema.columns c
                     where table_name = '"""+table+"""'
                       and table_schema = '"""+schema+"""'
                     order by ordinal_position""")

  l = []
  for r in cursor:
    f = Field (r[0], r[1], maxLength=r[2], isPk=r[5], isNullable=(r[4]!='no'))

    if r[3] is not None and r[3][0:7] == 'nextval':
      f.set_is_serial ( True )

    if f.type == 'USER-DEFINED':
        f.type = r[6]
    l.append( f )

  cursor.close()
  closeConnection(conn)

  return l

def getUniqueIndexesForTable(schema, table):
    conn = getConnection()
    cursor = conn.cursor()
    cursor.execute("""select indkey
                        from pg_class c,
                             pg_index i,
                             pg_namespace n
                       where i.indisunique
                         and c.relnamespace = n.oid
                         and c.oid = i.indrelid
                         and n.nspname = '""" + schema + """'
                         and c.relname = '""" + table + """'""")

    ret = []
    for r in cursor:
        if r[0] is not None and r[0][0] != '0' and r[0][0] != '-': 
            ret.append(r[0].split(' '))
    return ret

class Table ( object ):
    def __init__(self,schema,name,fields=[]):
        self.name = name
        self.schema = schema
        self.fields = fields
        self.associations = []
        self.children = []
        self.indexes = []

    def addField(self, f):
        self.fields.append(f)

    def addAssociation (self, a ):
        self.associations.append(a)

    def addChild (self, c ):
        self.children.append(c)

    def getName(self):
        return self.name

    def getSelectFieldListForType(self):
        l = []
        for f in self.fields:
            l.append(f.name)
        return ",".join(l)

    def getClassName(self):
        return java.camel_case(self.name)

    def setIndexes(self, v):
        self.indexes = v

class Association ( object ):
    def __init__(self, tableFrom, tableTo , colMap , doFollow = False):
        self.tableFrom = tableFrom
        self.tableTo = tableTo
        self.colMap = colMap        
        self.doFollow = doFollow

    def getSourceTuple(self):
        l = []
        for k in self.colMap:
            l.append(k)
        return ",".join(l)

    def getTargetTuple(self):
        l = []
        for k in self.colMap:
            l.append(self.colMap[k])
        return ",".join(l)

pg2javaMap        = { 'text': 'String', 'integer': 'Integer', 'bigint' : 'Long', 'timestamp without time zone' : 'Date', 'timestamp with time zone': 'Date', 'character varying' : 'String', 'smallint' : 'Integer' , 'character' : 'String', 'boolean' : 'Boolean' }
pg2javaMapNotNull = { 'text': 'String', 'integer': 'int',     'bigint' : 'long', 'timestamp without time zone' : 'Date', 'timestamp with time zone': 'Date', 'character varying' : 'String', 'smallint' : 'int',      'character' : 'String', 'boolean' : 'boolean' }

class Field(object):
    def __init__(self, name, type, maxLength = -1, isSerial = False, isPk = False, isEnum = False, isArray = False, isComplex = False, isNullable=True):
        self.isPk = isPk
        self.type = type
        self.maxLength = maxLength
        self.name = name
        self.isEnum = isEnum
        self.isArray = isArray
        self.isComplex = isComplex
        self.isSerial = isSerial
        self.isNullable = isNullable

    def set_is_serial(self,v):
      self.isSerial = v

    def get_java_type(self):
      if not self.type in pg2javaMap and not self.type in pg2javaMapNotNull:
        return java.camel_case(self.type)
      elif self.isNullable:
        return pg2javaMap[self.type]
      else:
        return pg2javaMapNotNull[self.type]


class Enum(object):
    def __init__(self, schema, name, values = []):
        self.name = name
        self.schema = schema
        self.values = values

def scaffold( table, package, path, opg ):
  java.generate_code( table, package, path )
  
  path += os.sep + 'database'
  if opg != '':
    path += os.sep + opg
  plpgsql.generate_code( table, path )

def create_for_table(schema,name,package):
  parentT = Table('public','parent',[Field('p_id','integer',isPk=True,isSerial=True), Field('p_name','text'), Field('p_first_name','text'), Field('p_parent_data_id','integer') ])
  parentDataT = Table('public','parent_data', [Field('pd_id','integer',isSerial=True,isPk=True),Field('pd_street','text'),Field('pd_city','text')])

  association = Association(parentT,parentDataT,{'p_parent_data_id':'pd_id'}, True)
  parentT.addAssociation( association )

  if package != '':
    package += '.'

  print plpgsql.create_pg_type ( parentT )
  print plpgsql.create_pg_type ( parentDataT )
  print java.create_java_type ( parentT, package )
  print java.create_java_type ( parentDataT, package )
  print plpgsql.create_sprocs( parentT )
  print java.create_sproc_service_interface( parentT, package )
  print java.create_sproc_service_implementation( parentT, package )

def main():
  argp = argparse.ArgumentParser(description='Scaffolder')
  argp.add_argument('-H', '--host', dest='host', default='localhost')
  argp.add_argument('-U', '--user', dest='user')
  argp.add_argument('-D', '--database', dest='database')
  argp.add_argument('-T', '--table', dest='table')
  argp.add_argument('-S', '--schema', dest='schema')
  argp.add_argument('-P', '--port', dest='port',default=5432)
  argp.add_argument('-o', '--output-directory', dest='path', default='output')
  argp.add_argument('-p', '--package', dest='package', default='')
  argp.add_argument('-g', '--opg', dest='opg', default='')
  args = argp.parse_args()

  if args.table == None:
    create_for_table('public','parent', args.package)
  else:
    setConnectionString( 'host='+args.host+' user='+args.user+' port='+ str(args.port) +' dbname=' + args.database )
    fields = getFieldsForTable(args.schema, args.table)
    t = Table ( args.schema, args.table, fields)
    i = getUniqueIndexesForTable(args.schema, args.table)
    t.setIndexes(i)
    scaffold ( t, args.package, args.path, args.opg )

if __name__ == "__main__":
    main()
