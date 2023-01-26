*___________________________________________________________________________________________________

crspGibbsBuildv01

Joel Hasbrouck

July, 2010

Run gibbs sampler over full crsp dataset

The program first builds the crsp sample (marking splits and changes in listing exchanges), and
then passes the crsp data to the estimation routines.
	
NOTE: RollGibbsLibrary02.sas must be run prior to this program, to compile the IML subroutines.

____________________________________________________________________________________________________;
options nocenter number ps=70 ls=130 nomprint notes;
options mautosource sasautos=('!SASROOT/sasautos',"$HOME/sasmacros",'.');
libname this "D:\Gibbs 2022 update\This\";
libname temp "D:\Gibbs 2022 update\Temp\";
libname crsp "D:\Gibbs 2022 update\CRSP\";


*____________________________________________________________________________________________________

	printds is a convenience macro for printing out the first few lines of dataset. 
	These printouts are for purposes of checking and debugging only. The logic would not be affected
	if all references to the macro were removed.
_____________________________________________________________________________________________________;
%macro printds(data=,obs=20, where=, contents=no);
%if %length(&data)=0 %then %let data=&syslast;
%if %upcase(&contents)=YES %then %do;
proc contents data=&data;
	title "Contents and first &obs observations for &data";
run;
%end;
proc print data=&data (obs=&obs
%if %length(&where)>0 %then where=(&where);
);
	title "&data &where";
	run;
title " ";
%mend printds;


%let startPermno=0;	*	If you need to restart the run from somewhere other than the first permno;

*proc datasets lib=crsp;
*	quit;
*%printds(data=crsp.dsenames);


*____________________________________________________________________________________________________

	Get days when exchcd changed (firm moved to a new listing exchange)
_____________________________________________________________________________________________________;
data temp.exch;
	set crsp.dsenames (rename=(exchcd=exchcd0));
	by permno notsorted exchcd0;
	retain startDate exchcd;
	if first.exchcd0 then do;
		startDate=namedt;
		exchcd=exchcd0;
	end;
	if last.exchcd0 then do;
		endDate=nameEndt;
		year = year(startDate);
		output;
		keep permno year startDate endDate exchcd shrcd;
		format startDate endDate date.;
	end;
run;
%printds(data=temp.exch);
	
*____________________________________________________________________________________________________

	Get days when there was split (change in cfacpr of more than 20%)
_____________________________________________________________________________________________________;
data temp.splits;
	set crsp.dsf;
	by permno notsorted cfacpr;
	year =year(date);
	cfacpr0 = lag(cfacpr);
	if first.permno then cfacpr0 = .;
	r = cfacpr/cfacpr0;
	if r>1.20 or r<0.8 then output;
	keep permno year date cfacpr;
run;
%printds(data=temp.splits);
	
*____________________________________________________________________________________________________

	Get index data
_____________________________________________________________________________________________________;
data dsi;
	set crsp.dsi;
	year = year(date);
	logret = log(1+vwretd);
	retain pm 0;
	pm = sum(pm, logret);
	if vwretd^=. then output;
	keep year date vwretd pm;
run;
*%printds(data=dsi);
	
*____________________________________________________________________________________________________

	Build daily file
_____________________________________________________________________________________________________;
data dsf / view=dsf;	*	Compute year;
	set crsp.dsf;
	year = year(date);
run;
*	Merge in splits and exchange changes;
data temp.dsf0;
	merge dsf (in=in1) temp.exch (in=in2 rename=(startDate=date exchcd=exchcd0 shrcd=shrcd0)) 
		temp.splits (in=in3 keep=permno year date);
	by permno year date;
	retain kSample exchcd shrcd;
	if first.year then kSample=1;
	if first.permno then do;
		exchcd=.;
		shrcd=.;
	end;
	if in2 then do;
		exchcd = exchcd0;
		shrcd = shrcd0;
	end;
	if not first.year and (in2 or in3) then kSample=kSample+1;
	TradeDay = prc>0;
	if in1 then output;
	keep permno year kSample date prc cfacpr exchcd shrcd ret retx TradeDay;
run;
*	Compute and merge in starting and ending dates;
data dateRange;
	set temp.dsf0;
	by permno year kSample;
	retain firstDate;
	if first.kSample then firstDate=date;
	if last.kSample then lastDate=date;
	format firstDate lastDate date.;
	if last.kSample then output;
	keep permno year kSample firstDate lastDate;
run;
data temp.dsf0;
	merge temp.dsf0 dateRange;
	by permno year kSample;
run;

*	Merge in index data;
proc sql;
	create table temp.dsf1 as select dsf.*, pm
		from temp.dsf0 as dsf, dsi where dsf.date=dsi.date
		order by permno, year, date;
	quit;

*	Initialize trade direction indicator q (recalling that q=0 ==> no trade);
options obs=max;
data temp.dsf2;
	set temp.dsf1;
	by permno;
	retain p 0;
	prcLast = lag(prc);
	if first.permno then do;
		p=0;
		prcLast = .;
	end;
	p = sum(p, log(1+ret));
	dp = abs(prc) - abs(prcLast);
	q = 1;
	if prc<0 then q=0;
	else do;
		q = sign(dp);
		if dp=. or dp=0 then q=1;
	end;
	if p^=. and pm^=. and q^=. then output;
run;
	

*____________________________________________________________________________________________________

	Tabulate counts of days and trading days.
_____________________________________________________________________________________________________;
proc means data=temp.dsf2 noprint;
	var TradeDay;
	output sum=nTradeDays out=temp.pys (drop=_type_ rename=(_freq_=nDays));
	id exchcd shrcd cfacpr firstDate lastDate;
	by permno year kSample;
run;
%printds;

data temp.dsf (index=(pys=(permno year kSample)));
	set temp.dsf2;
	keep permno year kSample p pm q;
run;
%printds;


*____________________________________________________________________________________________________

	This proc loops over all samples, calling the estimation routines.
_____________________________________________________________________________________________________;
options nonotes;
proc iml;
	start main;
	call streaminit(1234);
	reset storage=this.imlstor;	*	This contains the subroutines built in RollGibbsLibrary02.sas;
	load;

	reset printadv=1 log;
	use temp.pys;
	read all var {permno year kSample} where(nTradeDays>=60) into sample [colname=colSample];
	nSamples = nrow(sample);
	print 'nSamples=' nSamples;
	permno = sample[,1];
	year = sample[,2];
	kSample = sample[,3];
	outSet = j(1,7,.);
	varnames ={'permno','year','kSample','c','beta','varu','sdu'};
	create this.gibbsOut from outSet [colname=varnames];
	do iSample=1 to nSamples;
		thisPermno = permno[iSample];
		thisYear = year[iSample];
		thisKSample = kSample[iSample];
		if mod(iSample,500)=1 then do;
			t = time();
			ctime = putn(t,'time.');
			print ctime iSample '/' nSamples ': ' thisPermno thisYear thisKSample;
		end;
		if thisPermno>=&startPermno & thisYear>=1926 then do;
			use temp.dsf where (permno=thisPermno & year=thisYear & kSample=thisKSample);
			read all var {p pm q} into x [colname=colx];
			
			nSweeps = 1000;
			regDraw = 1;
			varuDraw = 1;
			qDraw = 1;
			nDrop = 200;
		
			call RollGibbsBeta(parmOut, x[,1],x[,2],x[,3], nSweeps, regDraw, varuDraw, qDraw, 0,0,0,0);
			
			p2 = parmOut[(nDrop+1):nSweeps,];
			p2 = p2 || sqrt(p2[,3]);
			pm = p2[+,]/(nSweeps-nDrop);
			outset = thisPermno || thisYear || thisKSample || pm;
			*print outset;
			setout this.gibbsOut;
			append from outSet;
		end;
	end;
	finish main;
run;
quit;
options notes;
proc print data=this.gibbsOut (obs=50);
run;

data this.crspGibbs;
	set this.gibbsOut;
run;
	

*____________________________________________________________________________________________________

	Compute descriptive statistics on the estimates.
_____________________________________________________________________________________________________;

proc means data=this.crspGibbs;
title "crspGibbs";
run;

*____________________________________________________________________________________________________

	Merge in supplementary descriptive data
_____________________________________________________________________________________________________;
data this.crspGibbsv01;
	merge this.crspGibbs temp.pys;
	by permno year ksample;
	label 
		permno='CRSP permno' year='Sample year' kSample='Sample number within year'
		c='c estimate' beta='beta estimate' varu='Var(u) estimate'
		sdu='SD(u) estimate'
		exchcd='CRSP exchcd for year/kSample' cfacpr='CRSP cfacpr for year/kSample'
		shrcd='CRSP shrcd for year/kSample' firstDate='Start date for year/kSample'
		lastDate='End date for year/kSample'
		nDays='Number of days in sample' nTradeDays='Number of days with realized trade';
	format permno 7. year 4. kSample 2. c 7.5 beta 8.4 varu 10.8 sdu 10.8 exchcd shrcd 2. 
		nDays 3. nTradeDays 3. cfacpr 8.6;
run;
proc contents data=this.crspGibbsv01 order=varnum;
run;
data _null_;
file 'crspgibbs.csv' delimiter=',' DSD DROPOVER lrecl=32767;
if _n_ = 1 then        /* write column names or labels */
do;
put
   "permno"
	','
   "year"
	','
   "kSample"
	','
    "c"
	','
   "beta"
	','
   "varu"
	','
   "sdu"
	','
   "exchcd"
	','
   "shrcd"
	','
   "CFACPR"
	','
   "firstDate"
	','
   "lastDate"
	','
   "nDays"
	','
   "nTradeDays";
end;
set  TMP1.crspgibbsv01   end=EFIEOD;
  format permno 7. ;
  format year 4. ;
  format kSample 2. ;
  format c 7.5 ;
  format beta 8.4 ;
  format varu 10.8 ;
  format sdu 10.8 ;
  format exchcd 2. ;
  format shrcd 2. ;
  format CFACPR 8.6 ;
  format firstDate date7. ;
  format lastDate date7. ;
  format nDays 3. ;
  format nTradeDays 3. ;
do;
  EFIOUT + 1;
  put permno @;
  put year @;
  put kSample @;
  put c @;
  put beta @;
  put varu @;
  put sdu @;
  put exchcd @;
  put shrcd @;
  put CFACPR @;
  put firstDate @;
  put lastDate @;
  put nDays @;
  put nTradeDays ;
  ;
end;
run;

