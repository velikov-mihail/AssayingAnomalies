function txt = num2words(num,opts,varargin)
% Convert a numeric to text with the number value written in English words (GB/IN/US).
%
% (c) 2014-2022 Stephen Cobeldick
%
% NUM2WORDS converts a numeric scalar into a char vector or string giving
% the number in English words, e.g. 1024 -> 'one thousand and twenty-four'.
%
%%% Syntax:
%  txt = num2words(num)
%  txt = num2words(num,opts)
%  txt = num2words(num,<name-value pairs>)
%
% The number format is based on: http://www.blackwasp.co.uk/NumberToWords.aspx
%
% Options control the number scale, number type, number precision, the
% string's character case, commas, hyphens, trailing zeros, and more.
%
%% Options %%
%
% The options may be supplied either
% 1) in a scalar structure, or
% 2) as a comma-separated list of name-value pairs.
%
% Field names and string values are case-insensitive. The following field
% names and values are permitted as options (**=default value):
%
% Field  | Permitted  |
% Name:  | Values:    | Description (example):
% =======|============|====================================================
% class  |'char'    **| Output <txt> is a character row vector (5->'five')
%        |'string'    | Output <txt> is a string scalar.       (5->"five")
% -------|------------|----------------------------------------------------
% type   |'decimal' **| Number words are cardinal/decimal (21->'twenty-one')
%        |'ordinal'   | Last number word is an ordinal    (21->'twenty-first')
%        |'highest'   | Uses the highest suitable multiplier, with decimal
%        |            | digits if required  (1.2e9->'one point two billion')
%        |'cheque'    | (1->'one dollar only', 0.1->'zero dollars and ten cents')
%        |'money'     | (1->'one dollar',      0.1->'ten cents')
% -------|------------|----------------------------------------------------
% scale  |'short'   **| Short scale, modern English   (1e9->'one billion')
%        |'long'      | Long scale, B.E. until 1970's (1e9->'one thousand million')
%        |'indian'    | Indian with Lakh and Crore    (1e9->'one hundred crore')
%        |'peletier'  | Most other European languages (1e9->'one milliard')
%        |'rowlett'   | Russ Rowlett's Greek-based    (1e9->'one gillion')
%        |'yllion'    | Donald Knuth's logarithmic    (1e9->'ten myllion')
% -------|------------|----------------------------------------------------
% case   |'lower'   **| Lowercase     ('one thousand and twenty-four')
%        |'upper'     | Uppercase     ('ONE THOUSAND AND TWENTY-FOUR')
%        |'title'     | Titlecase     ('One Thousand and Twenty-Four')
%        |'sentence'  | Sentence-case ('One thousand and twenty-four')
% -------|------------|----------------------------------------------------
% pos    | true       | With positive prefix ('positive one thousand and twenty-four')
%        | false    **|   No positive prefix ('one thousand and twenty-four')
% -------|------------|----------------------------------------------------
% and    | true     **| With 'and' before tens/ones ('one thousand and twenty-four')
%        | false      |   No 'and' before tens/ones ('one thousand twenty-four')
% -------|------------|----------------------------------------------------
% comma  | true     **| With comma separator ('one billion, two hundred million')
%        | false      |   No comma separator ('one billion two hundred million')
% -------|------------|----------------------------------------------------
% hyphen | true     **| With hyphen between tens and ones ('twenty-four')
%        | false      |   No hyphen between tens and ones ('twenty four')
% -------|------------|----------------------------------------------------
% trz    | true       | With trailing zeros  ('one point zero')
%        | false    **|   No trailing zeros  ('one')
% -------|------------|----------------------------------------------------
% One of the following two field names may be used, with a scalar value N:
% -------|------------|----------------------------------------------------
% order  | N          | Round <num> to the nearest 10^N. (0**) See Note 1.
% sigfig | N          | Round <num> to N significant figures.  See Note 2.
% -------|------------|----------------------------------------------------
% Only for types 'money' and 'cheque' (see the section "Money" below):
% -------|------------|----------------------------------------------------
% unit   | string     | The currency unit name  ('Dollar|'**)  See "Money"
% subunit| string     | The currency subunit name ('Cent|'**)  See "Money"
% -------|------------|----------------------------------------------------
%
% Note1: For <type> 'cheque' and 'money' the default order is that of the
%  smallest subunit (i.e. -2). For all other <type> the default order is 0.
% Note2: To provide the least-unexpected output, significant figures for numeric
%  classes single and double are internally limited to 6 and 15 digits respectively.
% Note3: The <scale> 'yllion' ignores the options <comma> and <and>.
% Note4: The <scale> 'indian' defaults to 'short' scale for values >= 10^21.
% Note5: Text names and values may be character vector or string scalar.
%
%% Money %%
%
% This function supports a money unit/subunit ratio of 1/100.
%
% Type:  | Description:
% =======|=================================================================
% cheque | Leading zeros. Suffix 'Only' if subunit==0 and <trz>==false.
% -------|-----------------------------------------------------------------
% money  | No leading zeros, even if <num> is zero.
% -------|-----------------------------------------------------------------
%
% Currency unit and subunit names are defined depending on the plural form:
% Plural:   | Input String Convention:   | Examples:
% ==========|============================|=================================
% invariant | 'InvariantName'            | 'Euro', 'Baht', 'Rand', 'Yuan'
% ----------|----------------------------|---------------------------------
% regular   | 'SingularName|'            | 'Pound|', 'Kopek|', 'Rupee|'
% ----------|----------------------------|---------------------------------
% irregular | 'SingularName|PluralName'  | 'Penny|Pence', 'Krone|Kroner'
% ----------|----------------------------|---------------------------------
%
%% Examples %%
%
% >> num2words(0)
% ans = 'zero'
%
% >> num2words(1024)
% ans = 'one thousand and twenty-four'
% >> num2words(-1024)
% ans = 'negative one thousand and twenty-four'
% >> num2words(1024, 'pos',true, 'case','title', 'hyphen',false)
% ans = 'Positive One Thousand and Twenty Four'
% >> num2words(1024, struct('type','ordinal', 'case','sentence'))
% ans = 'One thousand and twenty-fourth'
% >> num2words(1024, 'and',false, 'order',1) % round to the tens.
% ans = 'one thousand twenty'
%
% >> num2words(pi, 'order',-10) % round to tenth decimal digit
% ans = 'three point one four one five nine two six five three six'
%
% >> num2words(intmax('uint64'), 'sigfig',3, 'comma',false)
% ans = 'eighteen quintillion four hundred quadrillion'
% >> num2words(intmax('uint64'), 'sigfig',3, 'type','highest')
% ans = 'eighteen point four quintillion'
% >> num2words(intmax('uint64'), 'sigfig',3, 'scale','long')
% ans = 'eighteen trillion, four hundred thousand billion'
% >> num2words(intmax('uint64'), 'sigfig',3, 'case','title', 'scale','indian')
% ans = 'One Lakh, Eighty-Four Thousand Crore Crore'
% >> num2words(intmax('uint64'), 'order',17, 'case','upper', 'scale','yllion')
% ans = 'EIGHTEEN HUNDRED FORTY BYLLION'
%
% >> num2words(1234.56, 'type','cheque', 'unit','Euro')
% ans = 'one thousand, two hundred and thirty-four euro and fifty-six cents'
% >> num2words(1234.56, 'type','cheque', 'unit','Pound|', 'subunit','Penny|Pence')
% ans = 'one thousand, two hundred and thirty-four pounds and fifty-six pence'
%
% >> num2words(101, 'type','money', 'unit','Dalmatian|', 'case','title')
% >> num2words(1001, 'type','money', 'unit','Night|', 'case','title')
% >> sprintf('%s Under the Sea',num2words(2e4, 'type','money', 'unit','League|', 'case','title'))
%
%% Input and Output Arguments %%
%
%%% Inputs:
%  num  = NumericScalar (float, int, or uint), the value to convert to words.
%  opts = StructureScalar, with optional fields and values as per 'Options' above.
%  OR
%  <name-value pairs> = a comma-separated list of field names and associated values.
%
%%% Outputs:
%  txt = CharVector or StringScalar, the value of <num> using english words.
%
% See also WORDS2NUM NUM2WORDS_TEST NUM2WORDS_DEMO NUM2SIP NUM2BIP NUM2ORD NUM2YLLION
% COMPOSE STRING STRINGS INT2STR NUM2STR SPRINTF ARRAYFUN TTS

%% Input Wrangling %%
%
assert(isnumeric(num)&&isscalar(num),...
	'SC:num2words:num:NotScalarNumeric',...
	'First input <num> must be a numeric scalar.')
assert(isreal(num),...
	'SC:num2words:num:NotRealNumeric',...
	'First input <num> cannot be complex: %g%+gi',real(num),imag(num))
%
% Default option values:
stpo = struct(...
	'case','lower', 'type','decimal', 'scale','short', 'class','char',...
	'comma',true, 'hyphen',true, 'and',true, 'pos',false, 'trz',false,...
	'white',' ', 'order',0, 'sigfig',0,... In cells, as per post-parsing:
	'subunit',{{'Cent','Cents'}}, 'unit',{{'Dollar','Dollars'}});
%
% Check any supplied option fields and values:
switch nargin
	case 1 % no user-supplied options
		stpo.iso = true;
		stpo.mny = false;
	case 2 % options in a struct
		assert(isstruct(opts)&&isscalar(opts),...
			'SC:num2words:opts:NotScalarStruct',...
			'Second input <opts> structure must be scalar.')
		opts = structfun(@n2w1s2c,opts,'UniformOutput',false);
		stpo = n2wOptions(stpo,opts);
	otherwise % options as <name-value> pairs
		varargin = cellfun(@n2w1s2c,varargin,'UniformOutput',false);
		opts = struct(n2w1s2c(opts),varargin{:});
		assert(isscalar(opts),...
			'SC:num2words:options:ValueCellArray',...
			'Invalid <name-value> pairs: cell array values are not permitted.')
		stpo = n2wOptions(stpo,opts);
end
%
tmp = {stpo.white,'-'};
stpo.hyp = tmp{1+stpo.hyphen};
%
%% Order & Significant Figures %%
%
if isfinite(num)
	%
	if num==0
		mag = -1;
	elseif isfloat(num)
		mag = floor(log10(abs(num)));
	else % integer
		mag = numel(sprintf('%lu',abs(num)))-1;
	end
	%
	if stpo.iso % order
		odr = stpo.order;
		sgf = mag + 1 - odr;
	else % sigfig
		sgf = stpo.sigfig;
		odr = mag + 1 - sgf;
	end
	%
else % Inf or NaN
	%
	sgf = 0;
	odr = 0;
	%
end
%
%% Convert Numeric to String %%
%
isn = num<0 || (1/num)<0;
cls = class(num);
%
if sgf<1 % round one digit to a particular order
	%
	raw = sprintf('%+.0f',num/10^odr);
	%
	if any(strcmpi(raw,{'Inf','+Inf','-Inf'}))
		txt = 'Infinity';
		frc = [];
	elseif any(strcmpi(raw,{'NaN','+NaN','-NaN'}))
		txt = sprintf('Not%sa%sNumber',stpo.hyp,stpo.hyp);
		frc = [];
		stpo.pos = false;
	else % one digit
		pwr = odr;
		vec = raw(2:end);
		[txt,frc] = n2wParse(stpo,pwr,sgf,mag,vec-'0');
		%sgf = 1; % only if used as an output argument
	end
	%
elseif isfloat(num)
	%
	bfp = struct('double',15,'single',6);
	dfq = bfp.(cls);
	raw = sprintf('%#+.*e',min(sgf,dfq)-1,num);
	%
	ide = strfind(raw,'e');
	pwr = sscanf(raw(ide:end),'e%d');
	vec = raw([2,4:ide-1]);
	[txt,frc] = n2wParse(stpo,pwr,sgf,mag,vec-'0');
	%
else % integer
	%
	bit = sscanf(cls, '%*[ui]nt%u');
	pfx = {{},{},'%h','%h','%','%l'}; % {2,4,8,16,32,64} bit
	tmp = max(0,odr);
	raw = sprintf([pfx{log2(bit)},cls(1)], num/10^tmp);
	%
	pwr = numel(raw)-1-isn-(mag<0)+tmp;
	vec = raw(1+isn:min(sgf+isn,end));
	[txt,frc] = n2wParse(stpo,pwr,sgf,mag,vec-'0');
	%
end
%
%% Money or Ordinal %%
%
if stpo.mny
	odr = odr + (~stpo.iso && pwr>mag && ~strcmpi(txt,'Zero'));
	% Singular/plural form of unit/subunit currency name:
	fun = @(s,c)sprintf('%s%s%s',s,stpo.white,c{2-strcmpi(s,'One')});
else
	% Convert fractional digits into words:
	txt = sprintf('%s%s',txt,n2wFract(stpo,frc));
end
%
switch stpo.type
	case 'cheque'
		if odr>=0 || ~(stpo.trz || any(frc)) % Suffix with 'Only':
			txt = sprintf('%s%sOnly', fun(txt,stpo.unit),stpo.white);
		else % Always include leading units, even if they are zero:
			txt = sprintf('%s%sand%s%s', fun(txt,stpo.unit),stpo.white,...
				stpo.white,fun(n2wCents(stpo,frc),stpo.subunit));
		end
	case 'money'
		if odr>=0 || ~(stpo.trz || any(frc)) % Only the units:
			txt = fun(txt,stpo.unit);
		elseif strcmpi(txt,'Zero') % Only the subunits:
			txt = fun(n2wCents(stpo,frc),stpo.subunit);
		else % Mixed units and subunits:
			txt = sprintf('%s%sand%s%s', fun(txt,stpo.unit),stpo.white,...
				stpo.white,fun(n2wCents(stpo,frc),stpo.subunit));
		end
	case 'ordinal'
		expr = {'(ur|x|n|d|ro|re|h)$','One$','Two$','ree$','ve$','ht$','ne$','ty$'};
		repstr = {'$1th','First','Second','ird','fth','hth','nth','tieth'};
		txt = regexprep(txt,expr,repstr,'once','ignorecase');
end
%
%% Sign and Case %%
%
if isn
	txt = sprintf('Negative%s%s',stpo.white,txt);
elseif stpo.pos
	txt = sprintf('Positive%s%s',stpo.white,txt);
end
%
switch stpo.case
	case 'lower'
		txt = lower(txt);
	case 'upper'
		txt = upper(txt);
	case 'sentence'
		txt(2:end) = lower(txt(2:end));
end
%
if strcmpi(stpo.class,'string')
	txt = string(txt);
end
%
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%num2words
function stpo = n2wOptions(stpo,opts)
% Options check: only supported fieldnames with suitable option values.
%
opts = orderfields(opts);
stpo = orderfields(stpo);
ufc = fieldnames(opts);
dfc = fieldnames(stpo);
uvc = struct2cell(opts);
%
idf = ~cellfun(@(f)any(strcmpi(f,dfc)),ufc);
if any(idf)
	ufs = sprintf(' <%s>,',ufc{idf});
	dfs = sprintf(' <%s>,',dfc{:});
	error('SC:num2words:options:UnknownName',...
		'Unknown option:%s\b.\nField names must be:%s\b.',ufs,dfs)
end
%
% Logical options:
n2wLogic('and')
n2wLogic('comma')
n2wLogic('hyphen')
n2wLogic('pos')
n2wLogic('trz')
%
% Whitespace:
n2wWhite('white')
%
% String options:
n2wString('case', 'lower','upper','title','sentence')
n2wString('type', 'decimal','ordinal','highest','cheque','money')
n2wString('scale', 'long','short','peletier','rowlett','indian','yllion')
n2wString('class', 'char','string')
%
% Currency Names:
stpo.mny = any(strcmpi(stpo.type,{'cheque','money'}));
stpo.order = -2*stpo.mny;
n2wCurrency('subunit')
n2wCurrency('unit')
%
% Precision:
stpo.iso = [];
n2wDigit('order')
n2wDigit('sigfig')
stpo.iso = isempty(stpo.iso)||stpo.iso;
%
	function idx = n2wField(fld)
		% Options check: throw error for duplicate fieldnames.
		idx = strcmpi(fld,ufc);
		assert(nnz(idx)<2,...
			'SC:num2words:options:DuplicateName',...
			'Duplicate field names:%s\b.',sprintf(' <%s>,',ufc{idx}))
	end
	function n2wWhite(fld)
		% Options check: whitespace.
		idx = n2wField(fld);
		if any(idx)
			tmp = uvc{idx};
			assert(iscrv(tmp,isequal(tmp,'')),...
				sprintf('SC:num2words:%s:NotOneChar',fld),...
				'The <%s> value must be a scalar character or empty character.',fld)
			stpo.(fld) = tmp;
		end
	end
	function n2wLogic(fld)
		% Options check: logical scalar.
		idx = n2wField(fld);
		if any(idx)
			tmp = uvc{idx};
			assert(islogical(tmp)&&isscalar(tmp),...
				sprintf('SC:num2words:%s:NotScalarLogical',fld),...
				'The <%s> value must be a scalar logical.',fld)
			stpo.(fld) = tmp;
		end
	end
	function n2wString(fld,varargin)
		% Options check: string.
		idx = n2wField(fld);
		if any(idx)
			tmp = uvc{idx};
			if ~ischar(tmp)||~any(strcmpi(tmp,varargin))
				tmp = sprintf(' <%s>,',varargin{:});
				error(sprintf('SC:num2words:%s:UnknownValue',fld),...
					'The <%s> value must be one of:%s\b.',fld,tmp);
			end
			stpo.(fld) = lower(tmp);
		end
	end
	function n2wDigit(fld)
		% Options check: numeric scalar (order or significant figures).
		idx = n2wField(fld);
		if any(idx)
			assert(isempty(stpo.iso),...
				'SC:num2words:options:SigFigXorOrder',...
				'Only one of <order> or <sigfig> may be specified.')
			stpo.iso = strcmp(fld,'order');
			tmp = uvc{idx};
			assert(isnumeric(tmp)&&isscalar(tmp),...
				sprintf('SC:num2words:%s:NotScalarNumeric',fld),...
				'The <%s> value must be a scalar numeric.',fld)
			assert(isreal(tmp),...
				sprintf('SC:num2words:%s:NotRealNumeric',fld),...
				'The <%s> value cannot be complex: %g%+gi',fld,real(tmp),imag(tmp))
			assert(isfinite(tmp),...
				sprintf('SC:num2words:%s:NotFiniteNumeric',fld),...
				'The <%s> value must be finite: %g',fld,tmp)
			assert(fix(tmp)==tmp,...
				sprintf('SC:num2words:%s:NotWholeNumeric',fld),...
				'The <%s> value must be a whole number: %g',fld,tmp)
			assert(stpo.iso||(tmp>=1),...
				sprintf('SC:num2words:%s:NotPositiveNumeric',fld),...
				'The <%s> value must be positive: %g',fld,tmp)
			stpo.(fld) = double(tmp);
		end
	end
	function n2wCurrency(fld)
		% Options check: currency unit or subunit name.
		idx = n2wField(fld);
		if any(idx) && stpo.mny
			tmp = uvc{idx};
			assert(iscrv(tmp),...
				sprintf('SC:num2words:%s:NotCharRowNorStringScalar',fld),...
				'The <%s> value must be char row vector or string scalar.',fld)
			spl = regexp(tmp,'\|','split');
			assert(~isempty(spl{1}),...
				sprintf('SC:num2words:%s:NotValidCurrencyName',fld),...
				'The <%s> value does not define a currency name.',fld)
			assert(numel(spl)<3,...
				sprintf('SC:num2words:%s:NotValidCurrencyPlural',fld),...
				'The <%s> value may contain zero or one "|" character.',fld)
			if isscalar(spl) % invariant
				stpo.(fld) = spl([1,1]);
			elseif isempty(spl{2}) % regular
				stpo.(fld) = strcat(spl(1),{'','s'});
			else % irregular
				stpo.(fld) = spl;
			end
		end
	end
	function out = iscrv(txt,boo) % TXT is character (row vector || BOO)
		szv = size(txt);
		out = ischar(txt)&&((nargin>1&&boo)||(numel(szv)==2&&szv(1)==1));
	end
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%n2wOptions
function str = n2wCents(stpo,frc)
% Create the currency subunit string (defined as 1/100 of currency unit).
%
str = sprintf('%s%s',n2wWhole(stpo,1,frc(1:min(end,2))),n2wFract(stpo,frc(3:end)));
%
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%n2wCents
function [str,frc] = n2wParse(stpo,pwr,sgf,mag,dgt)
% Split digits vector into whole and fractional parts, convert whole part into words.
%
sgf = sgf + ((stpo.iso && pwr>mag) || (dgt(1)==0 && pwr==0));
% Pad with zeros or remove zeros from digits:
if stpo.trz % pad
	vec = [zeros(1,0-pwr),dgt,zeros(1,sgf-numel(dgt))];
elseif any(dgt) % remove
	vec = [zeros(1,0-pwr),dgt(1:find(dgt,1,'last'))];
else % remove all
	vec = [];
end
pwr = max(0,pwr);
%
% Split into whole digits and fractional digits:
if isempty(vec) || pwr>0 && strcmp(stpo.type,'highest')
	frc = [];
else % decimal, ordinal, cheque, money
	idf = (pwr-(0:numel(vec)-1))<0;
	frc = vec(idf);
	vec = vec(~idf);
end
%
% Convert whole digits into words:
str = n2wWhole(stpo,pwr,vec);
%
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%n2wParse
function str = n2wFract(stpo,frc)
% Convert a digits vector into decimal fraction string, preceded with 'point'.
%
if isempty(frc)
	str = '';
else
	cZer = {'Zero','One','Two','Three','Four','Five','Six','Seven','Eight','Nine'};
	str = sprintf('%sPoint%s',stpo.white,sprintf([stpo.white,'%s'],cZer{1+frc}));
end
%
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%n2wFract
function [mat,grp] = n2wShape(pwr,vec,N)
% Reshape input <vec> into a matrix with <N> rows, according to magnitude of order.
%
grp = mod(pwr-(0:numel(vec)-1),N);
mat = reshape([zeros(1,N-1-grp(1)),vec(:)',zeros(1,grp(end))],N,[]);
%
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%n2wShape
function [idy,frc] = n2wSplit(stpo,mat,grp,N)
% Split fractional parts from <mat>, index of (non-zero) columns to keep.
%
if strcmp(stpo.type,'highest')
	idy = true;
	frc = mat(N+1:end-grp(end));
else
	idy = any(mat,1);
	frc = [];
end
%
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%n2wSplit
function mat = n2wTeens(mat,N)
% Convert teens to ones within <mat>. N is tens row, N+1 is ones row.
%
idx = mat(N,:)==1;
mat(N+1,idx) = mat(N+1,idx) + 10;
mat(N+0,idx) = 0;
%
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%n2wTeens
function str = n2wWhole(stpo,pwr,vec)
% Convert a numeric vector of digits to a string with English number words.
%
cTen = {{},'Twenty','Thirty','Forty','Fifty','Sixty','Seventy','Eighty','Ninety'};
cOne = {'One','Two','Three','Four','Five','Six','Seven','Eight','Nine','Ten','Eleven','Twelve','Thirteen','Fourteen','Fifteen','Sixteen','Seventeen','Eighteen','Nineteen'};
%
if isempty(vec) || all(vec==0)
	str = 'Zero';
	return
elseif strcmp(stpo.scale,'yllion')
	str = n2wYllion(stpo,pwr,vec,cTen,cOne);
	return
elseif strcmp(stpo.scale,'indian') && pwr<21
	str = n2wIndian(stpo,pwr,vec,cTen,cOne);
	return
elseif strcmp(stpo.scale,'rowlett') % Derived from the work of Russ Rowlett and Sbiis Saibian.
	cPfx = {'M','G','Tetr','Pent','Hex','Hept','Okt','Enn','Dek','Hendek','Dodek','Trisdek','Tetradek','Pentadek','Hexadek','Heptadek','Oktadek','Enneadek','Icos','Icosihen','Icosid','Icositr','Icositetr','Icosipent','Icosihex','Icosihept','Icosiokt','Icosienn','Triacont','Triacontahen','Triacontad','Triacontatr','Triacontatetr','Triacontapent','Triacontahex','Triacontahept','Triacontaokt','Triacontaenn','Tetracont','Tetracontahen','Tetracontad','Tetracontatr','Tetracontatetr','Tetracontapent','Tetracontahex','Tetracontahept','Tetracontaokt','Tetracontaenn','Pentacont','Pentacontahen','Pentacontad','Pentacontatr','Pentacontatetr','Pentacontapent','Pentacontahex','Pentacontahept','Pentacontaokt','Pentacontaenn','Hexacont','Hexacontahen','Hexacontad','Hexacontatr','Hexacontatetr','Hexacontapent','Hexacontahex','Hexacontahept','Hexacontaokt','Hexacontaenn','Heptacont','Heptacontahen','Heptacontad','Heptacontatr','Heptacontatetr','Heptacontapent','Heptacontahex','Heptacontahept','Heptacontaokt','Heptacontaenn','Oktacont','Oktacontahen','Oktacontad','Oktacontatr','Oktacontatetr','Oktacontapent','Oktacontahex','Oktacontahept','Oktacontaokt','Oktacontaenn','Enneacont','Enneacontahen','Enneacontad','Enneacontatr','Enneacontatetr','Enneacontapent','Enneacontahex','Enneacontahept','Enneacontaokt','Enneacontaenn','Hect','Hectahen','Hectad'};
else % Derived from the work of John Conway, Allan Wechsler, Richard Guy, and Olivier Miakinen.
	cPfx = {'M','B','Tr','Quadr','Quint','Sext','Sept','Oct','Non','Dec','Undec','Duodec','Tredec','Quattuordec','Quindec','Sedec','Septendec','Octodec','Novendec','Vigint','Unvigint','Duovigint','Tresvigint','Quattuorvigint','Quinvigint','Sesvigint','Septemvigint','Octovigint','Novemvigint','Trigint','Untrigint','Duotrigint','Trestrigint','Quattuortrigint','Quintrigint','Sestrigint','Septentrigint','Octotrigint','Noventrigint','Quadragint','Unquadragint','Duoquadragint','Tresquadragint','Quattuorquadragint','Quinquadragint','Sesquadragint','Septenquadragint','Octoquadragint','Novenquadragint','Quinquagint','Unquinquagint','Duoquinquagint','Tresquinquagint','Quattuorquinquagint','Quinquinquagint','Sesquinquagint','Septenquinquagint','Octoquinquagint','Novenquinquagint','Sexagint','Unsexagint','Duosexagint','Tresexagint','Quattuorsexagint','Quinsexagint','Sesexagint','Septensexagint','Octosexagint','Novensexagint','Septuagint','Unseptuagint','Duoseptuagint','Treseptuagint','Quattuorseptuagint','Quinseptuagint','Seseptuagint','Septenseptuagint','Octoseptuagint','Novenseptuagint','Octogint','Unoctogint','Duooctogint','Tresoctogint','Quattuoroctogint','Quinoctogint','Sexoctogint','Septemoctogint','Octooctogint','Novemoctogint','Nonagint','Unnonagint','Duononagint','Trenonagint','Quattuornonagint','Quinnonagint','Senonagint','Septenonagint','Octononagint','Novenonagint','Cent','Uncent'};
end
%
% Reshape into 3xM matrix [Hundreds;Tens;Ones]:
row = 3;
[mat,grp] = n2wShape(pwr,vec,row);
% Split fractional part:
[idy,frc] = n2wSplit(stpo,mat,grp,row);
% Move teens into ones:
mat = n2wTeens(mat(:,idy),row-1);
%
mlt = floor(pwr/row)-(0:numel(idy));
mlt = mlt(idy);
% Indices for digits and punctuation:
iHun = mat(1,:)>0; % hundreds
iTen = mat(2,:)>0; % tens
iOne = mat(3,:)>0; % ones
iCom = iHun | mlt>0 | nnz(idy)==1; % commas
iAnd = iHun&(iTen|iOne) | ~iCom; % ands
%
% Indices for multipliers:
iPel = false;  % illiards
iTho = mlt==1; % thousands
switch stpo.scale
	case 'peletier'
		idx  = rem(mlt,2);
		iIon = 0==idx & mlt>1;
		iPel = 1==idx & mlt>1;
		mlt  = 1+floor(mlt/2);
	case 'long'
		iIon = mlt>=2;
		iTho = 1==rem(mlt,2);
		mlt  = 1+floor(mlt/2);
		iDif = ~diff(mlt);
		iIon(iDif) = false;
		iDif = [false,iDif]&~iHun;
		iAnd = iAnd | iDif;
		iCom = iCom & ~iDif;
	otherwise % short, rowlett
		iIon = mlt>=2; % illions
end
%
% Allocate all digits, multipliers and punctuation:
out = cell(15,size(mat,2));
out(:) = {''};
out(1,iCom&stpo.comma) = {','};
out(2,iCom) = {stpo.white};
out(3,iHun) = cOne(mat(1,iHun));
out(4,iHun) = {sprintf('%sHundred',stpo.white)};
out(5,iAnd) = {stpo.white};
out(6,iAnd&stpo.and) = {sprintf('and%s',stpo.white)};
out(7,iTen) = cTen(mat(2,iTen));
out(8,iOne&iTen) = {stpo.hyp};
out(9,iOne) = cOne(mat(3,iOne));
out{10,1} = n2wFract(stpo,frc);
out(11,iTho) = {stpo.white};
out(12,iTho) = {'Thousand'};
out(13,iIon|iPel) = {stpo.white};
out(15,iIon) = {'illion'};
out(15,iPel) = {'illiard'};
if any(iIon|iPel)
	out(14,iIon|iPel) = cPfx(mlt(iIon|iPel)-1);
end
%
str = sprintf('%s',out{3:end});
%
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%n2wWhole
function str = n2wYllion(stpo,pwr,vec,cTen,cOne)
% Donald Yllion's logarithmic scale (aka "-Yllion").
%
cMyr = {'Hundred','Myriad','Myllion','Byllion','Tryllion','Quadryllion','Quintyllion','Sextyllion'};
cMyr = strcat({stpo.white},cMyr);
%
% Reshape into 2xM matrix [Tens;Ones]:
row = 2;
[mat,grp] = n2wShape(pwr,vec,row);
% Split fractional part:
[idy,frc] = n2wSplit(stpo,mat,grp,row);
% Move teens into ones:
mat = n2wTeens(mat(:,idy),row-1);
%
mlt = floor(pwr/row)-(0:numel(idy));
mlt = [2*mlt(idy),NaN];
%
% Identify the multipliers for each group:
idm = floor(log2(mlt));
M = 1+max(0,idm(1));
idm(M,end) = 0;
for m = 2:M
	mlt = mlt - pow2(idm(m-1,:));
	idm(m,:) = floor(log2(mlt));
end
idm(~isfinite(idm)) = 0;
idx = 0>diff(idm,1,2);
idx(end:-1:1,:) = 0<(cumsum(idx,1)&idm(:,1:end-1));
idm(end:-1:1,:) = idm;
%
% Indices for digits:
iTen = mat(1,:)>0; % tens
iOne = mat(2,:)>0; % ones
%
% Allocate all digits, multipliers and punctuation:
N = nnz(idy);
out = cell(5+M,N);
out(:) = {''};
out([false(5,N);idx]) = cMyr(idm(idx));
out{5,end} = n2wFract(stpo,frc);
out(4,iOne) = cOne(mat(2,iOne));
out(3,iOne&iTen) = {stpo.hyp};
out(2,iTen) = cTen(mat(1,iTen));
out(1,:) = {stpo.white};
%
% Concatentate the strings together:
str = sprintf('%s',out{2:end});
%
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%n2wYllion
function str = n2wIndian(stpo,pwr,vec,cTen,cOne)
% Indian numbering using Lakh and Crore.
%
% Reshape into 9xN matrix [NaN;TenLakhs;Lakhs;NaN;TenThousands;Thousands;Hundreds;Tens;Ones]:
row = 7;
[mat([2:3,5:9],:),grp] = n2wShape(pwr,vec,row);
mat([1,4],:) = NaN;
% Reshape into 3xM matrix [Hundreds,Tens,Ones]:
idx = grp>4;
grp = grp+idx;
mat = mat(row+2-grp(1):end-grp(end));
pwr = pwr+2*floor(pwr/row)+idx(1);
row = 3;
[mat,grp] = n2wShape(pwr,mat,row);
% Split fractional part:
[idy,frc] = n2wSplit(stpo,mat,grp,row);
% Move teens into ones:
mat = n2wTeens(mat(:,idy),row-1);
%
mlt = floor(pwr/row)-(0:numel(idy));
mlt = mlt(idy);
grp = floor(mlt/row);
% Indices for digits:
iHun = mat(1,:)>0; % hundreds
iTen = mat(2,:)>0; % tens
iOne = mat(3,:)>0; % ones
%
% Indices for multipliers:
iLak = 2==mod(mlt,row); % lakhs
iTho = 1==mod(mlt,row); % thousands
iZer = 0==mod(mlt,row); % nones
iCro = [diff(grp)<0,grp(end)>0]; % crores
%
% Indices for punctuation:
iNaN = isnan(mat(1,:));
[~,~,iUni] = unique(grp(:));
iAnd = accumarray(iUni,~iNaN&any(mat(2:3,:),1),[],@any); % ands
iAnd = iAnd & accumarray(iUni,iNaN|mat(1,:)>0,[],@any);
iAnd = iZer & (~iNaN & iAnd(iUni).' | mlt==0 & nnz(idy)>1);
iCom = iHun | ~iAnd; % commas
%
% Allocate all digits, multipliers and punctuation:
out = cell(13,size(mat,2));
out(:) = {''};
out(1,iCom&stpo.comma) = {','};
out(2,iCom) = {stpo.white};
out(3,iHun) = cOne(mat(1,iHun));
out(4,iHun) = {sprintf('%sHundred',stpo.white)};
out(5,iAnd) = {stpo.white};
out(6,iAnd&stpo.and) = {sprintf('and%s',stpo.white)};
out(7,iTen) = cTen(mat(2,iTen));
out(8,iOne&iTen) = {stpo.hyp};
out(9,iOne) = cOne(mat(3,iOne));
out{10,1} = n2wFract(stpo,frc(~isnan(frc)));
out(11,iTho|iLak) = {stpo.white};
out(12,iTho) = {'Thousand'};
out(12,iLak) = {'Lakh'};
if any(iCro)
	fCro = @(n)repmat(sprintf('%sCrore',stpo.white),1,n);
	out(13,iCro) = arrayfun(fCro,grp(iCro),'UniformOutput',false);
end
%
str = sprintf('%s',out{3:end});
%
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%n2wIndian
function arr = n2w1s2c(arr)
% If scalar string then extract the character vector, otherwise data is unchanged.
if isa(arr,'string') && isscalar(arr)
	arr = arr{1};
end
end
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%n2w1s2c