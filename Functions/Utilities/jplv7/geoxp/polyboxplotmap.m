function [out]=polyboxplotmap(long,lat,var1,var2,varargin)
% PURPOSE: This function links a map and  a box and whiskers plots
%------------------------------------------------------------------------
% USAGE: out=polyboxplotmap(long,lat,var1,var2,carte,label,symbol)
%   where : 
%           long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%           var1 = n x 1 vector of the first variable to study
%           var2 = n x 1 vector of the second variable to study
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%------------------------------------------------------------------------
% MANUAL: Select points on  the box and whiskers plots by clicking with the left mouse button
%         Select quartiles on the box and whiskers plots by clicking with the left mouse button
%         Selection is lost when you switch graph
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% uses selectstat.m
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
name=inputname(3);
%creation d'un menu pour sauver
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save boxplotfich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
c=0;
l=0;
symbol=0;
% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        carte=varargin{1};
        c=1;
    end;
    if  t>=2 & ~isempty(varargin{2})
        label=varargin{2};
        l=1;
    end;
    if t==3 & ~isempty(varargin{3})
        symbol=varargin{3};
    end;
end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% Trace the map
Axis1=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');
%%%%%%%%%%%%%%

% calcule median, quantiles and other usefull figures
vsort=sort(var2);
N1=histc(var2,vsort');
valeurs=vsort(find(N1~=0));
med=zeros(length(valeurs),1);
q1=zeros(length(valeurs),1);
q3=zeros(length(valeurs),1);
frtbasse=zeros(length(valeurs),1);
ftrhaute=zeros(length(valeurs),1);
vadjmin=zeros(length(valeurs),1);
vadjmax=zeros(length(valeurs),1);
for i=1:length(valeurs)
    vectbox{i}=var1(find(var2==valeurs(i)));
    med(i)=prctile(vectbox{i},50);
    q1(i)=prctile(vectbox{i},25);
    q3(i)=prctile(vectbox{i},75);
end;
frtbasse=q1-1.5*(q3-q1);
frthaute=q3+1.5*(q3-q1);
for i=1:length(valeurs)
    v=vectbox{i};
    I=find(v>=frtbasse(i));
    vadjmin(i)=min(v(I));
    I=find(v<=frthaute(i));
    vadjmax(i)=max(v(I));
end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%    

% Trace box and whiskers plots
Axis2=subplot(1,2,2);
boxplot(var1,var2);
title(name);
axis manual;
subplot(Axis1);
axis manual;
Xlim2=get(Axis2,'XLim');
Ylim2=get(Axis2,'YLim');
%%%%%%%%%%%%%%%%%%%%%


% Main loop
BUTTON=0;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    PosAx2=get(Axis2,'Position');
    %redraw the graphs
    subplot(Axis2);
    hold on;
    cla;
    boxplot(var1,var2);
    axis manual;
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    if ~isempty(Iselect)
        v1=var1(Iselect);
        v2=var2(Iselect);
        v2s=sort(v2);
        Nv=histc(v2,v2s);
        vals=v2s(find(Nv~=0));
        for j=1:length(vals)
            H=[];
            J2=find(valeurs==vals(j));
            J=find(v2==vals(j));
            vect=v1(J);
            Iatyp=find(vect>frthaute(J2) | vect<frtbasse(J2));
            Ityp=find(vect<=frthaute(J2) & vect>=frtbasse(J2));
            if ~isempty(Iatyp)
                hold on;
                if symbol==1
                    plot(J2*ones(1,length(Iatyp)),vect(Iatyp),'b*');
                else
                    plot(J2*ones(1,length(Iatyp)),vect(Iatyp),'g+');
                end;
            end;
             if ~isempty(find(vect(Ityp)<q1(J2)))
                 rectangle('Position',[J2-0.25 vadjmin(J2) 0.5 q1(J2)-vadjmin(J2)],'FaceColor','g');
             end;
             if ~isempty(find(vect(Ityp)>=q1(J2) & vect(Ityp)<med(J2)))
                 rectangle('Position',[J2-0.25 q1(J2) 0.5 med(J2)-q1(J2)],'FaceColor','g');
             end;
             if ~isempty(find(vect(Ityp)>=med(J2) & vect(Ityp)<q3(J2)))
                 rectangle('Position',[J2-0.25 med(J2) 0.5 q3(J2)-med(J2)],'FaceColor','g');
             end;
             if ~isempty(find(vect(Ityp)>q3(J2)))
                 rectangle('Position',[J2-0.25 q3(J2) 0.5 vadjmax(J2)-q3(J2)],'FaceColor','g');
             end;
        end;
    end;
    hold off;
    subplot(Axis1);
    hold on;
    cla;
    if c==1
        plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect)
      plot(long(Iunselect),lat(Iunselect),'b.');
    end;
    if ~isempty(Iselect)
        if symbol==1
            plot(long(Iselect),lat(Iselect),'b*');
        else
            plot(long(Iselect),lat(Iselect),'g.');
        end;
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    [x,y,BUTTON]=ginput(1);
    currentpoint=get(1,'CurrentPoint');
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        obs=zeros(size(long,1),1);
    % box selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        if BUTTON~=3 & BUTTON~=2 
        obs=selectstat('polybox',obs,var1,frtbasse,frthaute,q1,med,q3,vectbox,valeurs,var2,x,y);
        end;
    end;
    %%%%%%%%%%%%%%%%%%
end;
out=obs;

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%